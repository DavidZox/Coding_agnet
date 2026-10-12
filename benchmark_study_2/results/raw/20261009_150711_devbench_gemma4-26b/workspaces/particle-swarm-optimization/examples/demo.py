import pso.pso_simple as pso
import pso.cost_functions as cost_functions

def main():
    # Define the problem parameters
    # Sphere function: f(x) = sum(x_i^2)
    # Minimum is at x = [0, 0, ..., 0]
    dim = 3
    initial_pos = [1.0, 1.0, 1.0]
    bounds = [[-5.0, 5.0] for _ in range(dim)]
    num_particles = 20
    maxiter = 50
    verbose = True

    print("Starting PSO optimization for Sphere function...")
    
    # Run the PSO algorithm
    err_best_g, pos_best_g = pso.minimize(
        cost_functions.sphere,
        initial_pos,
        bounds,
        num_particles,
        maxiter,
        verbose
    )

    print("\nOptimization Finished!")
    print(f"Best Solution Found: {pos_best_g}")
    print(f"Best Value Found: {err_best_g}")

if __name__ == "__main__":
    main()
