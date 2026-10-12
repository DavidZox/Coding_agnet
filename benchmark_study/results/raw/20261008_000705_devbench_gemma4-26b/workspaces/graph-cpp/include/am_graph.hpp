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
        arcMatrix = new int*[vexNum];
        for (int i = 0; i < vexNum; ++i) {
            arcMatrix[i] = new int[vexNum]();
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

    bool setVexer(std::vector<VertexType> vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) {
            return false;
        }
        for (int i = 0; i < _vexNum; ++i) {
            vexList[i] = vexes[i];
        }
        return true;
    }

    bool setArcs(std::vector<std::tuple<VertexType, VertexType, int>> arcs) {
        for (const auto& arc : arcs) {
            VertexType u_val = std::get<0>(arc);
            VertexType v_val = std::get<1>(arc);
            int weight = std::get<2>(arc);

            int u = locateVex(u_val);
            int v = locateVex(v_val);

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
