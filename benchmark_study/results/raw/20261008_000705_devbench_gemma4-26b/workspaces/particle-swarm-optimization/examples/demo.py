import pso.pso_simple as pso
import pso.cost_functions as cost_functions

def main():
    # Define the problem parameters
    # Initial position (x0) for particles (e.g., 2D space)
    initial_pos = [1.0, 1.0]
    
    # Bounds for the optimization problem: [[min_x, max_x], [min_y, max_y]]
    bounds = [[-5.0, 5.0], [-5.0, 5.0]]
    
    # PSO parameters
    num_particles = 20
    maxiter = 50
    verbose = True

    print("Starting PSO optimization with Sphere function...")
    
    # Run the minimization
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
