#ifndef AM_GRAPH_HPP
#define AM_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include <algorithm>
#include <stdexcept>

template <typename VertexType>
class AdjacencyMatrixGraph {
private:
    bool _isDirected;
    int _vexNum;
    int _arcNum;
    int** arcMatrix;
    std::vector<VertexType> vexList;

public:
    // Constructor
    AdjacencyMatrixGraph(int numVertices, int numArcs, bool isDirected)
        : _isDirected(isDirected), _vexNum(numVertices), _arcNum(numArcs) {
        
        // Allocate memory for the matrix (size x size)
        arcMatrix = new int*[numVertices];
        for (int i = 0; i < numVertices; ++i) {
            arcMatrix[i] = new int[numVertices];
            for (int j = 0; j < numVertices; ++j) {
                arcMatrix[i][j] = 0; // Initialize to 0
            }
        }
    }

    // Destructor to free memory
    ~AdjacencyMatrixGraph() {
        for (int i = 0; i < _vexNum; ++i) {
            delete[] arcMatrix[i];
        }
        delete[] arcMatrix;
    }

    // Sets the vertex list and returns success status
    bool setVexes(const std::vector<VertexType>& vexes) {
        if (vexes.size() != _vexNum) {
            return false;
        }
        vexList = vexes;
        return true;
    }

    // Sets the arcs and returns success status
    // Arc format: {start_vertex, end_vertex, weight}
    bool setArcs(const std::vector<std::tuple<int, int, int>>& arcs) {
        if (arcs.size() != _arcNum) {
            return false;
        }

        // Reset matrix to 0 before setting arcs
        for (int i = 0; i < _vexNum; ++i) {
            for (int j = 0; j < _vexNum; ++j) {
                arcMatrix[i][j] = 0;
            }
        }

        for (const auto& arc : arcs) {
            int u_idx = std::get<0>(arc);
            int v_idx = std::get<1>(arc);
            int weight = std::get<2>(arc);

            if (u_idx < 0 || u_idx >= _vexNum || v_idx < 0 || v_idx >= _vexNum) {
                return false; // Index out of bounds
            }

            // Set the edge weight in the matrix
            arcMatrix[u_idx][v_idx] = weight;

            // If undirected, set the reverse edge
            if (!_isDirected) {
                arcMatrix[v_idx][u_idx] = weight;
            }
        }
        return true;
    }

    // Finds the index (0 to _vexNum-1) corresponding to a VertexType value
    int locateVex(const VertexType& value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (vexList[i] == value) {
                return i;
            }
        }
        return -1; // Not found
    }

    // Output operator for Adjacency Matrix Graph
    friend std::ostream& operator<<(std::ostream& os, const AdjacencyMatrixGraph<VertexType>& graph) {
        os << "Adjacency Matrix：\n";
        for (int i = 0; i < graph._vexNum; ++i) {
            for (int j = 0; j < graph._vexNum; ++j) {
                os << graph.arcMatrix[i][j] << (j == graph._vexNum - 1 ? "" : " ");
            }
            os << "\n";
        }
        return os;
    }
};

#endif // AM_GRAPH_HPP
