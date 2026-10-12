import unittest
from pso.pso_simple import minimize, Particle
from pso.cost_functions import sphere

class TestPSOLogic(unittest.TestCase):
    def test_sphere_function_value(self):
        """Test if the sphere function returns correct values."""
        self.assertEqual(sphere([0, 0, 0]), 0.0)
        self.assertEqual(sphere([1, 2, 3]), 1**2 + 2**2 + 3**2)

    def test_particle_initialization(self):
        """Test if Particle initializes with correct attributes."""
        x0 = [1.0, 2.0]
        p = Particle(x0)
        self.assertEqual(p.position_i, [1.0, 2.0])
        self.assertEqual(p.velocity_i, [0.0, 0.0])
        self.assertEqual(p.pos_best_i, [1.0, 2.0])
        self.assertEqual(p.err_best_i, float('inf'))
        self.assertEqual(p.err_i, float('inf'))

    def test_particle_evaluate(self):
        """Test if Particle.evaluate updates error and personal best."""
        x0 = [1.0, 1.0]
        p = Particle(x0)
        # Sphere(1,1) = 2.0
        err = p.evaluate(sphere)
        self.assertEqual(err, 2.0)
        self.assertEqual(p.err_i, 2.0)
        self.assertEqual(p.err_best_i, 2.0)
        self.assertEqual(p.pos_best_i, [1.0, 1.0])

    def test_minimize_optimization(self):
        """Test if minimize can find the minimum of the sphere function."""
        x0 = [1.0, 1.0]
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        num_particles = 30
        maxiter = 100
        
        err_best_g, pos_best_g = minimize(
            sphere, x0, bounds, num_particles, maxiter, verbose=False
        )
        
        # For sphere function, the minimum is at (0,0) with error 0
        # We check if the error is very close to 0
        self.assertLess(err_best_g, 1e-2)
        # Check if position is close to (0,0)
        for val in pos_best_g:
            self.assertAlmostEqual(val, 0.0, places=1)

    def test_bounds_constraint(self):
        """Test if particles stay within bounds after update."""
        x0 = [4.5, 4.5]
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        p = Particle(x0)
        # Force a large velocity to push particle out of bounds
        p.velocity_i = [10.0, 10.0]
        p.update_position(bounds)
        
        self.assertEqual(p.position_i, [5.0, 5.0])

if __name__ == '__main__':
    unittest.main()
