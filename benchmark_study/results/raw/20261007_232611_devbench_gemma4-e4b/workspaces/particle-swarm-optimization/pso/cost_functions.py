def sphere(x):
    """
    Calculate the sphere function value for a given input vector x.
    The sphere function is defined as the sum of the squares of the elements in x.

    Args:
        x (list of floats): The input vector.

    Returns:
        float: The value of the sphere function (sum(x_i^2)).
    """
    return sum(xi**2 for xi in x)
