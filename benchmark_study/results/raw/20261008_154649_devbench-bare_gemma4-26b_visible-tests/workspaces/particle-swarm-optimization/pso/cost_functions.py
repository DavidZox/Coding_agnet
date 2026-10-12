def sphere(x):
    """
    Calculate the sphere function value for a given input vector x.
    :param x: list, input vector
    :return: float, the sphere function value
    """
    return sum(xi ** 2 for xi in x)
