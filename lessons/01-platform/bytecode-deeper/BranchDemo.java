public class BranchDemo {
    public static void main(String[] args) {
        System.out.println(absolute(-3));
        System.out.println(absolute(0));
        System.out.println(absolute(5));
    }

    static int absolute(int value) {
        if (value < 0) {
            return 0;
        }
        return value;
    }
}
