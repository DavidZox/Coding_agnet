from pso.pso_simple import minimize
from pso.cost_functions import sphere

def main():
    # Define the problem parameters
    initial_pos = [5.0, 5.0]
    bounds = [[-10.0, -10.0], [10.0, 10.0]]
    num_particles = 30
    maxiter = 100
    verbose = True

    # Run the PSO minimization
    print("Starting PSO optimization...")
    err_best_g, pos_best_g = minimize(
        sphere, 
        initial_pos, 
        bounds, 
        num_particles, 
        maxiter, 
        verbose
    )

    # Print the final results
    print("\nOptimization Finished!")
    print(f"Best Error: {err_best_g}")
    print(f"Best Position: {pos_best_g}")

if __name__ == "__main__":
    main()
