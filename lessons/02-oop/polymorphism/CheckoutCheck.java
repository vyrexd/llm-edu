void main() {
    Checkout checkout = new Checkout();
    expect(checkout.total(100, 2, new StandardFee()) == 130,
            "Стандартная доставка добавляет 30.");
    expect(checkout.total(100, 3, itemCount -> 5 * itemCount) == 115,
            "Переданная политика считает 5 за товар. Она должна получить количество товаров.");
    expect(checkout.total(210, 4, itemCount -> 0) == 210,
            "При бесплатной доставке итог равен сумме заказа.");
}

private static void expect(boolean condition, String message) {
    if (!condition) {
        throw new AssertionError(message);
    }
}
