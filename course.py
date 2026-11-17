"""Код проверок и локальный прогресс интерактивного учебника."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHAPTERS = json.loads((ROOT / "course.json").read_text(encoding="utf-8"))["chapters"]
EXERCISES = [exercise for chapter in CHAPTERS for exercise in chapter["exercises"]]
STATE = ROOT / ".java-course" / "progress.json"
JDK_MAJOR = 26
JAVA_TOOLS = ("java", "javac", "javap")


def java_files(exercise):
    return sorted((ROOT / exercise["file"]).parent.glob("*.java"))


def digest(exercise):
    fingerprint = hashlib.sha256()
    for path in java_files(exercise):
        fingerprint.update(hashlib.sha256(path.name.encode()).digest())
        fingerprint.update(hashlib.sha256(path.read_bytes()).digest())
    return fingerprint.hexdigest()


def read_progress():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"completed": [], "verified": None}


def save_progress(progress):
    STATE.parent.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=STATE.parent, delete=False
    ) as temp:
        json.dump(progress, temp, ensure_ascii=False, indent=2)
        temporary_path = Path(temp.name)
    try:
        temporary_path.replace(STATE)
    finally:
        temporary_path.unlink(missing_ok=True)


def current(progress):
    completed = set(progress["completed"])
    return next((exercise for exercise in EXERCISES if exercise["id"] not in completed), None)


def view():
    progress = read_progress()
    exercise = current(progress)
    awaiting_answer = bool(
        exercise and progress["verified"] == {"id": exercise["id"], "digest": digest(exercise)}
    )
    return {
        "completed": progress["completed"],
        "active": exercise["id"] if exercise else None,
        "awaitingAnswer": awaiting_answer,
    }


class CheckFailure(Exception):
    pass


def run(workdir, *command):
    result = subprocess.run(
        command, cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=15, check=False
    )
    if result.returncode:
        raise CheckFailure((result.stderr or result.stdout).strip()[:3000])
    return result.stdout.strip()


def require(condition, feedback):
    if not condition:
        raise CheckFailure(feedback)


def jdk_candidates():
    local = STATE.parent / "jdk"
    yield local / "bin"
    if sys.platform == "darwin":
        yield local / "Contents" / "Home" / "bin"
    if java_home := os.environ.get("JAVA_HOME"):
        yield Path(java_home) / "bin"
    if javac := shutil.which("javac"):
        yield Path(javac).resolve().parent
    if sys.platform == "darwin":
        try:
            java_home = run(ROOT, "/usr/libexec/java_home", "-F", "-v", str(JDK_MAJOR))
        except (CheckFailure, OSError, subprocess.TimeoutExpired):
            return
        yield Path(java_home) / "bin"


def find_jdk():
    suffix = ".exe" if os.name == "nt" else ""
    observed = []
    for bin_dir in dict.fromkeys(jdk_candidates()):
        tools = {name: bin_dir / (name + suffix) for name in JAVA_TOOLS}
        if not all(path.is_file() for path in tools.values()):
            continue
        try:
            versions = {
                name: run(ROOT, str(path), "-version" if name == "javap" else "--version")
                for name, path in tools.items()
            }
        except (CheckFailure, OSError, subprocess.TimeoutExpired):
            observed.append(f"{bin_dir}: инструменты не запустились")
            continue
        version_pattern = rf"^(?:(?:openjdk|java|javac|javap)\s+)?{JDK_MAJOR}(?=[.\s+-]|$)"
        if all(re.match(version_pattern, version) for version in versions.values()):
            return tools, versions
        observed.append(f"{bin_dir}: {versions['javac'] or 'версия javac не определилась'}")
    details = "\n" + "\n".join(observed) if observed else ""
    raise CheckFailure(f"Нужен JDK {JDK_MAJOR} с java, javac и javap из одного комплекта.{details}")


def doctor():
    result = {"requiredJdk": JDK_MAJOR, "python": sys.version.split()[0]}
    if sys.version_info < (3, 9):
        return {**result, "ok": False, "feedback": "Нужен Python 3.9 или новее."}
    try:
        tools, versions = find_jdk()
        with tempfile.TemporaryDirectory(prefix="java-course-doctor-") as directory:
            workdir = Path(directory)
            (workdir / "Ready.java").write_text(
                'public class Ready { public static void main(String[] args) { System.out.println("ready"); } }',
                encoding="utf-8",
            )
            run(workdir, str(tools["javac"]), "Ready.java")
            require(run(workdir, str(tools["java"]), "-cp", ".", "Ready") == "ready",
                    "Проверочный класс запустился с неожиданным результатом.")
            run(workdir, str(tools["javap"]), "-c", "Ready")
    except (CheckFailure, OSError, subprocess.TimeoutExpired) as error:
        return {**result, "ok": False, "feedback": str(error)}
    return {
        **result,
        "ok": True,
        "jdkHome": str(tools["java"].parent.parent),
        "tools": {name: str(path) for name, path in tools.items()},
        "versions": {name: version.splitlines()[0] for name, version in versions.items()},
    }


def verify(exercise, commands):
    exercise_id = exercise["id"]
    tools, _ = find_jdk()
    with tempfile.TemporaryDirectory(prefix="java-course-") as directory:
        workdir = Path(directory)

        def execute(tool, *args):
            commands.append([tool, *args])
            return run(workdir, str(tools[tool]), *args)

        # Snapshot sources so verification has no write side effects in the student's IDE.
        for source in java_files(exercise):
            (workdir / source.name).write_bytes(source.read_bytes())
        sources = sorted(path.name for path in workdir.glob("*.java"))
        execute("javac", "-encoding", "UTF-8", "-d", "classes", *sources)

        if exercise_id == "first-run":
            output = execute("java", "-cp", "classes", "Main")
            require(output == "Вторая версия",
                    f"После перекомпиляции ожидалось «Вторая версия». Вывод: {output or 'пусто'}.")
            return "Свежая компиляция и запуск → Вторая версия"

        if exercise_id == "compile":
            output = execute("java", "-cp", "classes", "Main")
            require(output == "240", f"Ожидалось 240. Программа вывела: {output or 'ничего'}.")
            source = workdir / "Main.java"
            text = source.read_text(encoding="utf-8")
            declaration = r"(\bint\s+minutes\s*=\s*)4(\s*;)"
            require(re.search(declaration, text), "Сохрани объявление int minutes = 4; для проверки других входов.")
            for minutes in (0, 9):
                variant = re.sub(declaration, lambda match: f"{match[1]}{minutes}{match[2]}", text, count=1)
                source.write_text(variant, encoding="utf-8")
                execute("javac", "-encoding", "UTF-8", "-d", "classes", source.name)
                result = execute("java", "-cp", "classes", "Main")
                require(result == str(minutes * 60),
                        f"Для {minutes} минут ожидается {minutes * 60}, получено {result or 'ничего'}.")
            return "javac → Main.class → java Main\n4 → 240, 0 → 0, 9 → 540"

        if exercise_id == "bytecode":
            output = execute("java", "-cp", "classes", "Main")
            require(output == "14", f"Ожидалось 14. Программа вывела: {output or 'ничего'}.")
            bytecode = execute("javap", "-classpath", "classes", "-c", "Main")
            main = re.search(r"public static void main\(java\.lang\.String\[\]\);(.*?)(?:\n  \S|\n})",
                             bytecode, re.DOTALL)
            invocation = re.search(r"\d+:\s+invokestatic[^\n]*// Method doubleValue:\(I\)I",
                                   main[1]) if main else None
            require(invocation, "Программа печатает 14. В байт-коде main пока нет вызова doubleValue.")
            return f"java Main → 14\njavap -c Main\n{invocation[0]}"

        if exercise_id == "encapsulation":
            execute("java", "-cp", "classes", "StockCheck")
            return "Склад прошёл проверку обычного резерва, отказа и граничных случаев."

        if exercise_id == "polymorphism":
            execute("java", "-cp", "classes", "CheckoutCheck")
            return "Проверены стандартная доставка, тариф за товар и бесплатная доставка."

        raise ValueError(f"Unknown exercise: {exercise_id}")


def check(exercise_id):
    progress = read_progress()
    exercise = current(progress)
    if exercise is None or exercise["id"] != exercise_id:
        return {"ok": False, "feedback": "Открой текущее упражнение."}

    before = digest(exercise)
    commands = []
    try:
        evidence = verify(exercise, commands)
        require(before == digest(exercise), "Файлы изменились во время проверки. Запусти её ещё раз.")
    except (CheckFailure, OSError, subprocess.TimeoutExpired) as error:
        if isinstance(error, subprocess.TimeoutExpired):
            feedback = "Команда Java превысила время ожидания. Проверь, завершается ли программа."
        elif isinstance(error, FileNotFoundError):
            feedback = f"Не удалось запустить JDK {JDK_MAJOR}. Выполни python3 course.py doctor."
        else:
            feedback = str(error)
        return {"ok": False, "feedback": feedback, "hint": exercise["hint"], "commands": commands}

    updated = read_progress()
    if current(updated) != exercise:
        return {"ok": False, "feedback": "Прогресс изменился. Открой текущее упражнение."}
    updated["verified"] = {"id": exercise_id, "digest": before}
    save_progress(updated)
    return {"ok": True, "feedback": evidence, "commands": commands}


def answer(exercise_id, choice):
    progress = read_progress()
    exercise = current(progress)
    if exercise is None or exercise["id"] != exercise_id:
        return {"ok": False, "feedback": "Открой текущее упражнение."}
    if progress["verified"] != {"id": exercise_id, "digest": digest(exercise)}:
        return {"ok": False, "feedback": "Сначала проверь текущую версию кода.", "needsCheck": True}
    if choice != exercise["answer"]:
        return {"ok": False, "feedback": "Попробуй объяснить, что в этом случае действительно изменится. Затем выбери ещё раз."}

    progress["completed"].append(exercise_id)
    progress["verified"] = None
    save_progress(progress)
    return {"ok": True, "feedback": exercise["explanation"], "progress": view()}


def catalog():
    return {
        "chapters": [
            {**chapter, "exercises": [
                {key: value for key, value in exercise.items() if key not in {"answer", "explanation"}}
                for exercise in chapter["exercises"]
            ]}
            for chapter in CHAPTERS
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("doctor")
    subcommands.add_parser("status")
    subcommands.add_parser("catalog")
    subcommands.add_parser("check").add_argument("exercise")
    response = subcommands.add_parser("answer")
    response.add_argument("exercise")
    response.add_argument("choice", type=int, help="Номер варианта с нуля.")
    args = parser.parse_args()

    if args.command == "doctor":
        result = doctor()
    elif args.command == "status":
        result = view()
    elif args.command == "catalog":
        result = catalog()
    elif args.command == "check":
        result = check(args.exercise)
    else:
        result = answer(args.exercise, args.choice)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
