def sphere(x: list) -> float:
    """
    Calculate the sphere function value for a given input vector x.
    The sphere function is defined as the sum of the squares of the elements in x: sum(x_i^2).

    Args:
        x: A list representing the input vector.

    Returns:
        The value of the sphere function as a float.
    """
    return sum(val ** 2 for val in x)
