def sphere(x: List[float]) -> float:
    """
    Calculate the sphere function value for a given input vector x.

    The sphere function is defined as: f(x) = sum(x_i^2)

    :param x: The input vector (list of floats).
    :return: The value of the sphere function (float).
    """
    return sum(val ** 2 for val in x)
