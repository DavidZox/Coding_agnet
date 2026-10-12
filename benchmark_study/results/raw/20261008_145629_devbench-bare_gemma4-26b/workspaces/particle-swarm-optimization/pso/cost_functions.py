def sphere(x: list) -> float:
    """
    Calculate the sphere function value for a given input vector x.
    The sphere function is defined as the sum of squares of the components.

    Args:
        x (list): The input vector.

    Returns:
        float: The calculated sphere function value.
    """
    return sum(val ** 2 for val in x)
