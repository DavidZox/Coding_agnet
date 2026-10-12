#ifndef AM_GRAPH_HPP
#define AM_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>

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

    bool setVexes(const std::vector<VertexType>& vexes) {
        if (vexes.size() != _vexNum) {
            return false;
        }
        for (int i = 0; i < _vexNum; ++i) {
            vexList[i] = vexes[i];
        }
        return true;
    }

    bool setArcs(const std::vector<std::tuple<VertexType, VertexType, int>>& arcs) {
        for (const auto& arc : arcs) {
            int start = locateVex(std::get<0>(arc));
            int end = locateVex(std::get<1>(arc));
            int weight = std::get<2>(arc);
            if (start == -1 || end == -1) {
                return false;
            }
            arcMatrix[start][end] = weight;
            if (!_isDirected) {
                arcMatrix[end][start] = weight;
            }
        }
        return true;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyMatrixGraph& graph) {
        os << "Adjacency Matrix:\n";
        for (int i = 0; i < graph._vexNum; ++i) {
            for (int j = 0; j < graph._vexNum; ++j) {
                os << graph.arcMatrix[i][j] << " ";
            }
            os << "\n";
        }
        os << "Adjacency Table:\n";
        for (int i = 0; i < graph._vexNum; ++i) {
            os << graph.vexList[i] << "\t";
            for (int j = 0; j < graph._vexNum; ++j) {
                if (graph.arcMatrix[i][j] != 0) {
                    os << j << "\t" << graph.arcMatrix[i][j] << "\t->\t";
                }
            }
            os << "^\n";
        }
        return os;
    }
};

#endif // AM_GRAPH_HPP
