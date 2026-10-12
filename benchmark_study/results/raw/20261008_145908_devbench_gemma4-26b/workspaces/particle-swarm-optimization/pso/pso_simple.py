import math
import random

class Particle:
    def __init__(self, x0):
        self.position_i = list(x0)
        self.velocity_i = [0.0 for _ in range(len(x0))]
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
        # Standard PSO velocity update formula:
        # v = w*v + c1*r1*(pbest - x) + c2*r2*(gbest - x)
        # Using common default values: w=0.5, c1=1.5, c2=1.5
        w = 0.5
        c1 = 1.5
        c2 = 1.5
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
        # Randomize initial position within bounds
        start_pos = [random.uniform(b[0], b[1]) for b in bounds]
        particles.append(Particle(start_pos))

    err_best_g = float('inf')
    pos_best_g = list(x0)

    for iteration in range(maxiter):
        for p in particles:
            # Evaluate
            p.evaluate(costFunc)
            
            # Update global best
            if p.err_i < err_best_g:
                err_best_g = p.err_i
                pos_best_g = list(p.position_i)

        if verbose:
            print(f"Iteration {iteration + 1}/{maxiter}: Best Error = {err_best_g}")

        # Update particles
        for p in particles:
            p.update_velocity(pos_best_g)
            p.update_position(bounds)

    if verbose:
        print(f"Optimization finished.")
        print(f"Best Solution: {pos_best_g}")
        print(f"Best Value: {err_best_g}")

    return err_best_g, pos_best_g
