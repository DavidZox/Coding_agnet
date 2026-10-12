#ifndef AM_GRAPH_HPP
#define AM_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>

template <typename VertexType>
class AdjacencyMatrixGraph {
public:
    AdjacencyMatrixGraph(int vexNum, int arcNum, bool isDirected) 
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum) {
        arcMatrix = new int*[vexNum];
        for (int i = 0; i < vexNum; ++i) {
            arcMatrix[i] = new int[vexNum];
            for (int j = 0; j < vexNum; ++j) {
                arcMatrix[i][j] = 0;
            }
        }
        vexList = new VertexType[vexNum];
    }

    ~AdjacencyMatrixGraph() {
        for (int i = 0; i < _vexNum; ++i) {
            delete[] arcMatrix[i];
        }
        delete[] arcMatrix;
        delete[] vexList;
    }

    int locateVex(VertexType value) {
        for (int i = 0; i < _vexNum; ++i) {
            if (vexList[i] == value) {
                return i;
            }
        }
        return -1;
    }

    bool setVexes(std::vector<VertexType> vexes) {
        if (vexes.size() + 1 > static_cast<size_t>(_vexNum)) {
            return false;
        }
        for (size_t i = 0; i < vexes.size(); ++i) {
            vexList[i + 1] = vexes[i];
        }
        return true;
    }

    bool setArcs(std::vector<std::tuple<VertexType, VertexType, int>> arcs) {
        for (const auto& arc : arcs) {
            int u = locateVex(std::get<0>(arc));
            int v = locateVex(std::get<1>(arc));
            int w = std::get<2>(arc);
            if (u != -1 && v != -1) {
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

private:
    bool _isDirected;
    int _vexNum;
    int _arcNum;
    int** arcMatrix;
    VertexType* vexList;
};

#endif
