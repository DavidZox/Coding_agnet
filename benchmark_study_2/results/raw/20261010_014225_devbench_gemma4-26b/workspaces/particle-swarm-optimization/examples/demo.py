from pso.pso_simple import minimize
from pso.cost_functions import sphere

def main():
    # Define the problem parameters
    # Sphere function: f(x) = sum(x_i^2)
    # Optimal solution is at [0, 0, ..., 0]
    
    initial_pos = [1.0, 1.0, 1.0]
    bounds = [(-5.0, 5.0), (-5.0, 5.0), (-5.0, 5.0)]
    num_particles = 30
    maxiter = 100
    verbose = True

    print("Starting PSO optimization on Sphere function...")
    print(f"Bounds: {bounds}")
    print(f"Particles: {num_particles}, Max Iterations: {maxiter}\n")

    # Run the minimization
    err_best_g, pos_best_g = minimize(
        costFunc=sphere,
        x0=initial_pos,
        bounds=bounds,
        num_particles=num_particles,
        maxiter=maxiter,
        verbose=verbose
    )

    print("\n--- Final Result ---")
    print(f"Best Error Found: {err_best_g}")
    print(f"Best Position Found: {pos_best_g}")

if __name__ == "__main__":
    main()
