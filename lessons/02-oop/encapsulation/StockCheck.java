void main() {
    Stock stock = new Stock();
    expect(stock.available() == 3, "Новый склад должен содержать 3 штуки.");
    expect(stock.reserve(2), "На складе хватало товара для резерва 2 штук.");
    expect(stock.available() == 1, "После резерва 2 штук должна остаться 1.");
    expect(!stock.reserve(2), "Запрос на 2 штуки должен быть отклонён, если осталась 1.");
    expect(stock.available() == 1, "Отклонённый запрос изменил остаток.");
    expect(!stock.reserve(0), "Запрос с нулевым количеством должен быть отклонён.");
    expect(stock.available() == 1, "Нулевой запрос изменил остаток.");
    expect(!stock.reserve(-1), "Отрицательное количество должно быть отклонено.");
    expect(stock.available() == 1, "Отрицательный запрос изменил остаток.");
    expect(stock.reserve(1) && stock.available() == 0, "Последнюю штуку можно зарезервировать.");
    expect(!stock.reserve(1) && stock.available() == 0, "Пустой склад должен отклонить резерв.");
}

private static void expect(boolean condition, String message) {
    if (!condition) {
        throw new AssertionError(message);
    }
}
