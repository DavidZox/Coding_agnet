from pso.pso_simple import minimize
from pso.cost_functions import sphere

def main():
    # Define the problem parameters
    initial_pos = [1.0, 1.0]
    bounds = [(-5.0, 5.0), (-5.0, 5.0)]
    num_particles = 30
    maxiter = 50
    verbose = True

    # Run the PSO algorithm
    print("Starting PSO optimization...")
    err_best_g, pos_best_g = minimize(
        costFunc=sphere,
        x0=initial_pos,
        bounds=bounds,
        num_particles=num_particles,
        maxiter=maxiter,
        verbose=verbose
    )

    print("\nFinal Result:")
    print(f"Best Error: {err_best_g}")
    print(f"Best Position: {pos_best_g}")

if __name__ == "__main__":
    main()
