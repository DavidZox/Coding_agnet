import random

class Particle:
    def __init__(self, x0: list):
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

    def update_velocity(self, pos_best_g: list):
        # Standard PSO velocity update: v = w*v + c1*r1*(pbest - x) + c2*r2*(gbest - x)
        # Using common default coefficients: w=0.5, c1=1.5, c2=1.5
        w = 0.5
        c1 = 1.5
        c2 = 1.5
        for i in range(len(self.velocity_i)):
            r1 = random.random()
            r2 = random.random()
            cognitive = c1 * r1 * (self.pos_best_i[i] - self.position_i[i])
            social = c2 * r2 * (pos_best_g[i] - self.position_i[i])
            self.velocity_i[i] = w * self.velocity_i[i] + cognitive + social

    def update_position(self, bounds: list):
        for i in range(len(self.position_i)):
            self.position_i[i] += self.velocity_i[i]
            # Clamp position to bounds
            if self.position_i[i] < bounds[i][0]:
                self.position_i[i] = bounds[i][0]
            elif self.position_i[i] > bounds[i][1]:
                self.position_i[i] = bounds[i][1]

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose=False):
    dim = len(x0)
    particles = []
    
    # Initialize particles
    for _ in range(num_particles):
        # Random initial position within bounds
        start_pos = [random.uniform(bounds[i][0], bounds[i][1]) for i in range(dim)]
        particles.append(Particle(start_pos))

    pos_best_g = list(x0)
    err_best_g = float('inf')

    for iteration in range(maxiter):
        for p in particles:
            p.evaluate(costFunc)
            if p.err_best_i < err_best_g:
                err_best_g = p.err_best_i
                pos_best_g = list(p.pos_best_i)

        if verbose:
            print(f"Iteration {iteration}: Best Error = {err_best_g}")

        for p in particles:
            p.update_velocity(pos_best_g)
            p.update_position(bounds)

    return err_best_g, pos_best_g
