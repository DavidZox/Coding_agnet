#ifndef SHAPE_H
#define SHAPE_H

class Shape {
public:
    // Constructor
    Shape();

    // Destructor
    virtual ~Shape();

    // Virtual function to calculate area
    virtual double calcArea() const = 0;
};

#endif // SHAPE_H
