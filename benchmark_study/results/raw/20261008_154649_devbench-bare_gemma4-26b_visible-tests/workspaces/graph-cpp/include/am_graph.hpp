#ifndef AM_GRAPH_HPP
#define AM_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
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
    AdjacencyMatrixGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum) {
        arcMatrix = new int*[_vexNum];
        for (int i = 0; i < _vexNum; ++i) {
            arcMatrix[i] = new int[_vexNum];
            for (int j = 0; j < _vexNum; ++j) {
                arcMatrix[i][j] = 0;
            }
        }
        vexList = new VertexType[_vexNum];
    }

    ~AdjacencyMatrixGraph() {
        for (int i = 0; i < _vexNum; ++i) {
            delete[] arcMatrix[i];
        }
        delete[] arcMatrix;
        delete[] vexList;
    }

    int locateVex(VertexType value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (vexList[i] == value) {
                return i;
            }
        }
        return -1;
    }

    bool setVexes(const std::vector<VertexType>& vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) {
            throw std::out_of_range("Vertex count mismatch");
        }
        for (int i = 0; i < _vexNum; ++i) {
            vexList[i] = vexes[i];
        }
        return true;
    }

    bool setArcs(const std::vector<std::tuple<int, int, int>>& arcs) {
        for (const auto& arc : arcs) {
            int u = std::get<0>(arc);
            int v = std::get<1>(arc);
            int w = std::get<2>(arc);

            if (u >= 0 && u < _vexNum && v >= 0 && v < _vexNum) {
                arcMatrix[u][v] = w;
                if (!_isDirected) {
                    arcMatrix[v][u] = w;
                }
            }
        }
        return true;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyMatrixGraph& graph) {
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

#endif
