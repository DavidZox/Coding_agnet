from pso.pso_simple import minimize
from pso.cost_functions import sphere

if __name__ == "__main__":
    # Define the initial position, bounds, number of particles, and maximum iterations
    initial_position = [0.0, 0.0]
    bounds = [(-10, 10), (-10, 10)]
    num_particles = 30
    max_iterations = 100
    verbose = True

    # Run the PSO algorithm
    best_error, best_position = minimize(sphere, initial_position, bounds, num_particles, max_iterations, verbose)

    # Print the final result
    print(f"Best Solution: {best_position}, Best Error: {best_error}")
