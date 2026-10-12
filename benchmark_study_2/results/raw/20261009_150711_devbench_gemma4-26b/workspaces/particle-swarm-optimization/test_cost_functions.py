from pso.cost_functions import sphere

def test_sphere():
    # Test cases: (input_list, expected_output)
    test_cases = [
        ([0, 0, 0], 0.0),
        ([1, 2, 3], 14.0),
        ([-1, -1], 2.0),
        ([0.5], 0.25),
        ([1, -1], 2.0),
        ([], 0.0)
    ]

    for x, expected in test_cases:
        result = sphere(x)
        assert abs(result - expected) < 1e-9, f"Test failed for x={x}: expected {expected}, got {result}"
    
    print("All tests for sphere function passed!")

if __name__ == "__main__":
    test_sphere()
