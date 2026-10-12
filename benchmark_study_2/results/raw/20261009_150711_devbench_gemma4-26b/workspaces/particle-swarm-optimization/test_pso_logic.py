import unittest
from pso.pso_simple import minimize
from pso.cost_functions import sphere

class TestPSOLogic(unittest.TestCase):
    def test_minimize_sphere(self):
        """
        Test if the minimize function can converge to a value close to 0
        using the sphere function.
        """
        # Configuration
        x0 = [1.0, 1.0]
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        num_particles = 30
        maxiter = 100
        verbose = False

        # Execution
        err_best_g, pos_best_g = minimize(
            sphere, 
            x0, 
            bounds, 
            num_particles, 
            maxiter, 
            verbose
        )

        # Verification
        # The sphere function minimum is at [0, 0] with value 0.
        # We check if the error is sufficiently small.
        self.assertLess(err_best_g, 1e-2, f"Error {err_best_g} is not close to 0")
        self.assertEqual(len(pos_best_g), len(x0), "Result position dimension mismatch")

if __name__ == "__main__":
    unittest.main()
