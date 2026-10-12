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

public:
    AdjacencyMatrixGraph(int numVertices, int numArcs, bool isDirected)
        : _isDirected(isDirected), _vexNum(numVertices), _arcNum(numArcs) {
        
        if (_vexNum <= 0) {
            throw std::invalid_argument("Number of vertices must be positive.");
        }

        // Allocate memory for the matrix (rows)
        arcMatrix = new int*[_vexNum];
        for (int i = 0; i < _vexNum; ++i) {
            // Allocate memory for each row (columns)
            arcMatrix[i] = new int[_vexNum];
            for (int j = 0; j < _vexNum; ++j) {
                arcMatrix[i][j] = 0;
            }
        }

        // Allocate memory for vertex list
        vexList = new VertexType[_vexNum];
        for (int i = 0; i < _vexNum; ++i) {
            // Initialize with a placeholder or handle based on usage context
            // For now, we rely on setVexes to populate it.
        }
    }

    ~AdjacencyMatrixGraph() {
        // Free memory for the matrix
        for (int i = 0; i < _vexNum; ++i) {
            delete[] arcMatrix[i];
        }
        delete[] arcMatrix;
        // Free memory for vertex list
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
    bool setVexes(std::vector<VertexType>& vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) {
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
    bool setArcs(std::vector<std::tuple<int, int, int>>& arcs) {
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
                // Set the weight in the matrix
                arcMatrix[u][v] = weight;

                // If undirected, set the symmetric entry
                if (!_isDirected) {
                    arcMatrix[v][u] = weight;
                }
            } else {
                // Invalid vertex index in arc definition
                return false;
            }
        }
        return true;
    }

    /**
     * @brief Locates the index of a given vertex value.
     * @param value The vertex value to locate.
     * @return The index of the vertex, or -1 if not found.
     */
    int locateVex(VertexType value) {
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

    // --- End of Getter methods ---


    /**
     * @brief Overloads the stream insertion operator for printing the Adjacency Matrix.
     * @param os The output stream.
     * @param graph The AdjacencyMatrixGraph object.
     * @return The modified output stream.
     */
    friend std::ostream& operator<<(std::ostream& os, const AdjacencyMatrixGraph<VertexType>& graph) {
        os << "Adjacency Matrix：\n";
        for (int i = 0; i < graph.getVexNum(); ++i) {
            for (int j = 0; j < graph.getVexNum(); ++j) {
                os << graph.getArcMatrix()[i][j] << (j == graph.getVexNum() - 1 ? "" : " ");
            }
            os << "\n";
        }
        return os;
    }
};

#endif // AM_GRAPH_HPP
