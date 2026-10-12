def sphere(x):
    """
    Calculate the sphere function value for a given input vector x.
    The sphere function is the sum of squares of the elements in the vector.

    Args:
        x (list or array-like): The input vector.

    Returns:
        float: The calculated sphere function value.
    """
    return sum(xi ** 2 for xi in x)
