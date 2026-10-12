#ifndef AM_GRAPH_HPP
#define AM_GRAPH_HPP

#include <iostream>
#include <vector>
#include <tuple>
#include <iomanip>

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
        // Allocate arcMatrix
        arcMatrix = new int*[_vexNum];
        for (int i = 0; i < _vexNum; ++i) {
            arcMatrix[i] = new int[_vexNum];
            for (int j = 0; j < _vexNum; ++j) {
                arcMatrix[i][j] = 0;
            }
        }
        // Allocate vexList
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
            return false;
        }
        for (int i = 0; i < _vexNum; ++i) {
            vexList[i] = vexes[i];
        }
        return true;
    }

    bool setArcs(const std::vector<std::tuple<VertexType, VertexType, int>>& arcs) {
        // Reset matrix first if needed, but usually setArcs is called once
        for (const auto& arc : arcs) {
            int u = locateVex(std::get<0>(arc));
            int v = locateVex(std::get<1>(arc));
            int weight = std::get<2>(arc);

            if (u != -1 && v != -1) {
                arcMatrix[u][v] = weight;
                if (!_isDirected) {
                    arcMatrix[v][u] = weight;
                }
            } else {
                return false;
            }
        }
        return true;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyMatrixGraph& graph) {
        os << "Adjacency Matrix：" << std::endl;
        for (int i = 0; i < graph._vexNum; ++i) {
            for (int j = 0; j < graph._vexNum; ++j) {
                os << graph.arcMatrix[i][j] << (j == graph._vexNum - 1 ? "" : " ");
            }
            os << std::endl;
        }
        return os;
    }
};

#endif
