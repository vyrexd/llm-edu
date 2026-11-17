public final class StandardFee implements FeePolicy {
    @Override
    public int fee(int itemCount) {
        return 30;
    }
}
