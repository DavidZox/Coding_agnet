"""Battery helpers (pure Python, no ROS dependency)."""

EMPTY_VOLTAGE = 22.0  # 6S Li-ion pack, fully discharged
FULL_VOLTAGE = 25.2  # 6S Li-ion pack, fully charged


def percent(voltage, empty=EMPTY_VOLTAGE, full=FULL_VOLTAGE):
    """Linear estimate of the state of charge, clamped to 0..100."""
    if full <= empty:
        raise ValueError('full must be greater than empty')
    value = (voltage - empty) / (full - empty) * 100.0
    return max(0.0, min(100.0, value))
