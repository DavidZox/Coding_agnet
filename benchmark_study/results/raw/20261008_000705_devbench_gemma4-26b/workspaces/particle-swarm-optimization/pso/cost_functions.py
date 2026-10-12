def sphere(x):
    """
    Calculate the sphere function value for a given input vector x.
    The sphere function is the sum of squares of the components of x.

    Args:
        x (list): A list of numbers representing the input vector.

    Returns:
        float: The sum of squares of the elements in x.
    """
    return sum(val ** 2 for val in x)
