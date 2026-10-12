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
    VertexType* vexList;

    // Helper to allocate and initialize the matrix
    void initializeMatrix(int numVertices) {
        arcMatrix = new int*[numVertices];
        for (int i = 0; i < numVertices; ++i) {
            arcMatrix[i] = new int[numVertices];
            for (int j = 0; j < numVertices; ++j) {
                arcMatrix[i][j] = 0;
            }
        }
    }

    // Helper to deallocate memory
    void cleanupMatrix() {
        if (arcMatrix) {
            for (int i = 0; i < _vexNum; ++i) {
                delete[] arcMatrix[i];
            }
            delete[] arcMatrix;
            arcMatrix = nullptr;
        }
    }

public:
    AdjacencyMatrixGraph(int numVertices, int numArcs, bool isDirected)
        : _isDirected(isDirected), _vexNum(numVertices), _arcNum(numArcs) {
        
        // Allocate space for vertex list (assuming vertex indices start from 0 up to numVertices-1)
        vexList = new VertexType[_vexNum];
        // Initialize vertices (e.g., to 0 or some default value if not set later)
        for(int i = 0; i < _vexNum; ++i) {
            vexList[i] = static_cast<VertexType>(i); // Defaulting to index as vertex value for simplicity in this implementation context
        }

        initializeMatrix(_vexNum);
    }

    ~AdjacencyMatrixGraph() {
        cleanupMatrix();
        delete[] vexList;
    }

    // Prevent copying and assignment
    AdjacencyMatrixGraph(const AdjacencyMatrixGraph&) = delete;
    AdjacencyMatrixGraph& operator=(const AdjacencyMatrixGraph&) = delete;

    /**
     * @brief Sets the vertex list for the graph.
     * @param vexes The vector containing vertex values.
     * @return true if successful, false otherwise.
     */
    bool setVexer(const std::vector<VertexType>& vexes) {
        if (static_cast<long unsigned int>(vexes.size()) != static_cast<long unsigned int>(_vexNum)) {
            return false;
        }
        for (int i = 0; i < _vexNum; ++i) {
            vexList[i] = vexes[i];
        }
        return true;
    }

    /**
     * @brief Sets the arcs (edges) in the graph.
     * @param arcs A vector of tuples: {start_vertex_index, end_vertex_index, weight}.
     * @return true if successful, false otherwise.
     */
    bool setArcs(const std::vector<std::tuple<int, int, int>>& arcs) {
        // Reset matrix to 0 before setting arcs
        for (int i = 0; i < _vexNum; ++i) {
            for (int j = 0; j < _vexNum; ++j) {
                arcMatrix[i][j] = 0;
            }
        }

        for (const auto& arc : arcs) {
            int u = std::get<0>(arc);
            int v = std::get<1>(arc);
            int weight = std::get<2>(arc);

            if (u >= 0 && u < _vexNum && v >= 0 && v < _vexNum) {
                // For undirected graph, set both (u, v) and (v, u)
                if (!_isDirected) {
                    arcMatrix[u][v] = weight;
                    arcMatrix[v][u] = weight;
                } else {
                    // For directed graph, only set (u, v)
                    arcMatrix[u][v] = weight;
                }
                _arcNum++;
            }
        }
        return true;
    }

    /**
     * @brief Finds the index (location) of a given vertex value.
     * @param value The vertex value to locate.
     * @return The index of the vertex, or -1 if not found.
     */
    int locateVex(VertexType value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (vexList[i] == value) {
                return i;
            }
        }
        return -1;
    }

    // --- Getter methods added to resolve compilation errors ---

    /**
     * @brief Gets the number of vertices in the graph.
     * @return The number of vertices.
     */
    int getVexNum() const {
        return _vexNum;
    }

    /**
     * @brief Gets the adjacency matrix.
     * @return A pointer to the adjacency matrix (int**).
     */
    int** getArcMatrix() const {
        return arcMatrix;
    }

    /**
     * @brief Gets the list of vertex values.
     * @return A pointer to the vertex list (VertexType*).
     */
    VertexType* getVexList() const {
        return vexList;
    }

    // --- End of Getter methods ---


    /**
     * @brief Overload for printing the adjacency matrix.
     */
    friend std::ostream& operator<<(std::ostream& os, const AdjacencyMatrixGraph<int>& graph) {
        os << "Adjacency Matrix：\n";
        for (int i = 0; i < graph._vexNum; ++i) {
            for (int j = 0; j < graph._vexNum; ++j) {
                os << graph.arcMatrix[i][j] << " ";
            }
            os << "\n";
        }
        return os;
    }
};

#endif // AM_GRAPH_HPP
