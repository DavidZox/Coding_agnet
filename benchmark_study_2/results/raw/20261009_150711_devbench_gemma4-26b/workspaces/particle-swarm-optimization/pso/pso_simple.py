import random

class Particle:
    def __init__(self, x0):
        self.position_i = list(x0)
        self.velocity_i = [0.0 for _ in x0]
        self.pos_best_i = list(x0)
        self.err_best_i = float('inf')
        self.err_i = float('inf')

    def evaluate(self, costFunc):
        self.err_i = costFunc(self.position_i)
        if self.err_i < self.err_best_i:
            self.err_best_i = self.err_i
            self.pos_best_i = list(self.position_i)
        return self.err_i

    def update_velocity(self, pos_best_g):
        # Standard PSO velocity update parameters
        w = 0.5  # inertia weight
        c1 = 1.5 # cognitive coefficient
        c2 = 1.5 # social coefficient
        
        for i in range(len(self.position_i)):
            r1 = random.random()
            r2 = random.random()
            cognitive = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            self.velocity_i[i] = w * self.velocity_i[i] + cognitive + social

    def update_position(self, bounds):
        for i in range(len(self.position_i)):
            self.position_i[i] += self.velocity_i[i]
            # Clamp position to bounds
            if self.position_i[i] < bounds[i][0]:
                self.position_i[i] = bounds[i][0]
            elif self.position_i[i] > bounds[i][1]:
                self.position_i[i] = bounds[i][1]

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose=True):
    # Initialize particles
    particles = []
    for _ in range(num_particles):
        # Random initial position within bounds
        initial_pos = [random.uniform(b[0], b[1]) for b in bounds]
        particles.append(Particle(initial_pos))

    # Initialize global best with a particle's position or x0
    # To ensure consistency with the requirement of finding the best, 
    # we'll initialize err_best_g based on the first particle's evaluation or a very high value.
    pos_best_g = list(x0)
    err_best_g = float('inf')

    for iteration in range(maxiter):
        for particle in particles:
            # Evaluate
            err = particle.evaluate(costFunc)
            
            # Update global best
            if err < err_best_g:
                err_best_g = err
                pos_best_g = list(particle.position_i)

        if verbose:
            print(f"Iteration {iteration}: Best Error = {err_best_g}")

        # Update particles
        for particle in particles:
            particle.update_velocity(pos_best_g)
            particle.update_position(bounds)

    return err_best_g, pos_best_g

if __name__ == "__main__":
    # Simple local test if run directly
    from pso.cost_functions import sphere
    test_x0 = [1.0, 1.0]
    test_bounds = [(-5.0, 5.0), (-5.0, 5.0)]
    err, pos = minimize(sphere, test_x0, test_bounds, 30, 100, True)
    print(f"Final Best Error: {err}")
    print(f"Final Best Position: {pos}")
