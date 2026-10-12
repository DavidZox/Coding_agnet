from pso.cost_functions import sphere

def test_sphere():
    # Test case 1: Zero vector
    assert sphere([0, 0, 0]) == 0.0
    
    # Test case 2: Simple positive integers
    assert sphere([1, 2, 3]) == 1**2 + 2**2 + 3**2  # 1 + 4 + 9 = 14
    
    # Test case 3: Negative numbers
    assert sphere([-1, -2]) == (-1)**2 + (-2)**2  # 1 + 4 = 5
    
    # Test case 4: Floating point numbers
    assert abs(sphere([0.5, 0.5]) - 0.5) < 1e-9  # 0.25 + 0.25 = 0.5
    
    # Test case 5: Single element
    assert sphere([5]) == 25.0

    print("All sphere function tests passed!")

if __name__ == "__main__":
    test_sphere()
