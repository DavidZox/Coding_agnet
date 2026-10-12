def sphere(x: list) -> float:
    """
    Calculate the sphere function value for a given input vector x.

    The sphere function is defined as the sum of the squares of its components:
    f(x) = sum(x_i^2)

    Args:
        x: A list of floats representing the input vector.

    Returns:
        The value of the sphere function (float).
    """
    return sum(xi**2 for xi in x)
