import random

class Particle:
    def __init__(self, x0):
        self.__position_i = x0
        self.__velocity_i = [0.0 for _ in range(len(x0))]
        self.__pos_best_i = x0.copy()  # Initialize pos_best_i with the initial position
        self.__err_best_i = float('inf')
        self.__err_i = float('inf')

    def evaluate(self, costFunc):
        self.__err_i = costFunc(self.__position_i)

        if self.__err_i < self.__err_best_i:
            self.__pos_best_i = self.__position_i.copy()
            self.__err_best_i = self.__err_i

    def update_velocity(self, pos_best_g):
        w = 0.5
        c1 = 1.5
        c2 = 1.5

        for i in range(len(self.__velocity_i)):
            r1 = random.random()
            r2 = random.random()

            vel_cognitive = c1 * r1 * (self.__pos_best_i[i] - self.__position_i[i])
            vel_social = c2 * r2 * (pos_best_g[i] - self.__position_i[i])
            self.__velocity_i[i] = w * self.__velocity_i[i] + vel_cognitive + vel_social

    def update_position(self, bounds):
        for i in range(len(self.__position_i)):
            self.__position_i[i] = self.__position_i[i] + self.__velocity_i[i]

            if self.__position_i[i] > bounds[i][1]:
                self.__position_i[i] = bounds[i][1]

            if self.__position_i[i] < bounds[i][0]:
                self.__position_i[i] = bounds[i][0]

def minimize(costFunc, x0, bounds, num_particles, maxiter, verbose):
    err_best_g = float('inf')
    pos_best_g = x0.copy()  # Initialize pos_best_g with the initial position

    swarm = [Particle(x0) for _ in range(num_particles)]

    for i in range(maxiter):
        for particle in swarm:
            particle.evaluate(costFunc)

            if particle.__err_i < err_best_g:
                pos_best_g = list(particle.__position_i)
                err_best_g = float(particle.__err_i)

        for particle in swarm:
            particle.update_velocity(pos_best_g)
            particle.update_position(bounds)

        if verbose:
            print(f"Iteration {i}: Best Solution = {pos_best_g}, Best Error = {err_best_g}")

    return (err_best_g, pos_best_g)
