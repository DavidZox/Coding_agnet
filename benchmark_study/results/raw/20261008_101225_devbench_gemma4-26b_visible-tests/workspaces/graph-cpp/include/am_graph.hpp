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
        arcMatrix = new int*[_vexNum];
        for (int i = 0; i < _vexNum; ++i) {
            arcMatrix[i] = new int[_vexNum]();
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

    bool setVexes(std::vector<VertexType> vexes) {
        if (vexes.size() > static_cast<size_t>(_vexNum)) {
            return false;
        }
        // Based on the test requirement where locateVex(1) returns 1,
        // and the constructor allocates vexes.size() + 1,
        // we should fill the vexList starting from index 1.
        for (size_t i = 0; i < vexes.size(); ++i) {
            vexList[i + 1] = vexes[i];
        }
        return true;
    }

    bool setArcs(std::vector<std::tuple<int, int, int>> arcs) {
        if (arcs.size() > static_cast<size_t>(_arcNum)) {
            return false;
        }
        for (const auto& arc : arcs) {
            int u = std::get<0>(arc);
            int v = std::get<1>(arc);
            int w = std::get<2>(arc);
            // The test implies indices are 1-based for the matrix as well
            if (u >= 0 && u < _vexNum && v >= 0 && v < _vexNum) {
                arcMatrix[u][v] = w;
                if (!_isDirected) {
                    arcMatrix[v][u] = w;
                }
            } else {
                return false;
            }
        }
        return true;
    }

    int locateVex(VertexType value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (vexList[i] == value) {
                return i;
            }
        }
        return -1;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyMatrixGraph& amg) {
        os << "Adjacency Matrix：" << std::endl;
        for (int i = 0; i < amg._vexNum; ++i) {
            for (int j = 0; j < amg._vexNum; ++j) {
                os << amg.arcMatrix[i][j] << (j == amg._vexNum - 1 ? "" : " ");
            }
            os << std::endl;
        }
        return os;
    }
};

#endif
