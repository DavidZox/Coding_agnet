import sys
import os

# Add the project root directory to sys.path to allow importing the 'pso' package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pso.pso_simple import minimize
from pso.cost_functions import sphere

def main():
    # Define the problem parameters
    x0 = [1.0, 1.0, 1.0]  # Initial position (used to determine dimension)
    bounds = [(-5.0, 5.0), (-5.0, 5.0), (-5.0, 5.0)]  # Bounds for each dimension
    num_particles = 30
    maxiter = 50
    verbose = True

    print("Starting PSO optimization for the sphere function...")
    print(f"Parameters: num_particles={num_particles}, maxiter={maxiter}, bounds={bounds}")
    print("-" * 50)

    # Run the PSO algorithm
    err_best_g, pos_best_g = minimize(
        sphere, 
        x0, 
        bounds, 
        num_particles, 
        maxiter, 
        verbose=verbose
    )

    print("-" * 50)
    print("Optimization Finished!")
    print(f"Best Error Found: {err_best_g}")
    print(f"Best Position Found: {pos_best_g}")

if __name__ == "__main__":
    main()
