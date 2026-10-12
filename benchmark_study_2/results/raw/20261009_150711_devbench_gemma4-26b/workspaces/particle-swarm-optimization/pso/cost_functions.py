def sphere(x):
    """
    Calculate the sphere function value for a given input vector x.
    The sphere function is the sum of squares of the components of x.

    Args:
        x (list): A list of numbers representing the position vector.

    Returns:
        float: The sum of squares of the elements in x.
    """
    return sum(val ** 2 for val in x)

if __name__ == "__main__":
    # Simple test script to verify the sphere function
    test_cases = [
        ([0, 0, 0], 0.0),
        ([1, 2, 3], 14.0),
        ([-1, -1], 2.0),
        ([0.5], 0.25)
    ]

    for x, expected in test_cases:
        result = sphere(x)
        assert abs(result - expected) < 1e-9, f"Test failed for x={x}: expected {expected}, got {result}"
    
    print("All tests passed!")
