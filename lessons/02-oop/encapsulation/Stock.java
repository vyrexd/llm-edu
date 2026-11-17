public final class Stock {
    private int available = 3;

    public int available() {
        return available;
    }

    public boolean reserve(int quantity) {
        available -= quantity;
        return true;
    }
}
