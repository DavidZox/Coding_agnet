import unittest
import sys
import os

from pso import pso_simple
from pso.cost_functions import sphere


class TestPSO(unittest.TestCase):

    def test_evaluate(self):
        """
        This test checks whether the evaluate method correctly evaluates the particle's position using the given cost function.
        """
        # Create a particle
        particle = pso_simple.Particle([1, 2])

        # Define a cost function
        def cost_func(position):
            return sum(position)

        # Evaluate the particle's position using the cost function
        particle.evaluate(cost_func)

        # Check if the particle's best position and error are updated correctly
        self.assertEqual(particle.pos_best_i, [1, 2])
        self.assertEqual(particle.err_best_i, 3)


if __name__ == '__main__':
    unittest.main()