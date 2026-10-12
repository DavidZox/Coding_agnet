#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include <algorithm>
#include "stack.hpp"
#include "queue.hpp"

template <typename VertexType>
class AdjacencyListGraph {
private:
    struct ArcNode {
        int adjVex;
        int weight;
        ArcNode* next;
        ArcNode(int v, int w, ArcNode* n) : adjVex(v), weight(w), next(n) {}
    };

    struct _vNode {
        VertexType v;
        _vNode* next;
        _vNode(VertexType val, _vNode* n) : v(val), next(n) {}
    };

    bool _isDirected;
    int _vexNum;
    int _arcNum;
    _vNode* _vexList;
    std::vector<ArcNode*> _adjList;

    void clear() {
        // This is handled by setVexer and setArcs
    }

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum), _vexList(nullptr) {
        _adjList.resize(vexNum, nullptr);
    }

    ~AdjacencyListGraph() {
        for (int i = 0; i < _vexNum; ++i) {
            ArcNode* curr = _adjList[i];
            while (curr) {
                ArcNode* temp = curr;
                curr = curr->next;
                delete temp;
            }
        }
        _vNode* currV = _vexList;
        while (currV) {
            _vNode* temp = currV;
            currV = currV->next;
            delete temp;
        }
    }

    int locateVex(VertexType value) {
        _vNode* curr = _vexList;
        int idx = 0;
        while (curr) {
            if (curr->v == value) return idx;
            curr = curr->next;
            idx++;
        }
        return -1;
    }

    bool setVexer(std::vector<VertexType> vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) return false;
        
        // Clean existing
        _vNode* currV = _vexList;
        while(currV) {
            _vNode* temp = currV;
            currV = currV->next;
            delete temp;
        }
        _vexList = nullptr;
        _vNode* tail = nullptr;

        for (const auto& v : vexes) {
            _vNode* newNode = new _vNode(v, nullptr);
            if (!_vexList) {
                _vexList = newNode;
            } else {
                tail->next = newNode;
            }
            tail = newNode;
        }
        return true;
    }

    bool setArcs(std::vector<std::tuple<VertexType, VertexType, int>> arcs) {
        // Clear existing arcs
        for (int i = 0; i < _vexNum; ++i) {
            ArcNode* curr = _adjList[i];
            while (curr) {
                ArcNode* temp = curr;
                curr = curr->next;
                delete temp;
            }
            _adjList[i] = nullptr;
        }

        int actualArcCount = 0;
        for (const auto& arc : arcs) {
            int u = locateVex(std::get<0>(arc));
            int v = locateVex(std::get<1>(arc));
            int w = std::get<2>(arc);

            if (u != -1 && v != -1) {
                _adjList[u] = new ArcNode(v, w, _adjList[u]);
                actualArcCount++;
                if (!_isDirected) {
                    _adjList[v] = new ArcNode(u, w, _adjList[v]);
                    actualArcCount++;
                }
            }
        }
        _arcNum = actualArcCount;
        return true;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> res;
        if (_vexNum == 0) return res;

        std::vector<bool> visited(_vexNum, false);
        Stack<int> s;

        // Start from the first vertex in the list
        _vNode* startNode = _vexList;
        if (!startNode) return res;
        
        s.push(0); // Using index 0 as starting point

        while (!s.empty()) {
            int u = s.top();

            if (!visited[u]) {
                visited[u] = true;
                
                // Find vertex value from index
                _vNode* currV = _vexList;
                for(int i=0; i<u; ++i) currV = currV->next;
                res.push_back(currV->v);

                // To match standard DFS behavior (visiting neighbors in order), 
                // we should push neighbors to stack in reverse order.
                std::vector<ArcNode*> neighbors;
                ArcNode* currA = _adjList[u];
                while(currA) {
                    neighbors.push_back(currA);
                    currA = currA->next;
                }
                
                for (int i = neighbors.size() - 1; i >= 0; --i) {
                    if (!visited[neighbors[i]->adjVex]) {
                        s.push(neighbors[i]->adjVex);
                    }
                }
            }
            s.pop();
        }
        return res;
    }

    std::vector<VertexType> bfs() {
        if (!_vexList) return {};
        return bfs(_vexList->v);
    }

    std::vector<VertexType> bfs(VertexType startVal) {
        std::vector<VertexType> res;
        int startIdx = locateVex(startVal);
        if (startIdx == -1) return res;

        std::vector<bool> visited(_vexNum, false);
        Queue<int> q;

        visited[startIdx] = true;
        q.push(startIdx);

        while (!q.empty()) {
            int u = q.pop();
            
            _vNode* currV = _vexList;
            for(int i=0; i<u; ++i) currV = currV->next;
            res.push_back(currV->v);

            // To match BFS order (visiting neighbors in order), 
            // we need to traverse the adjacency list in the order they were added.
            // Since we added them to the head (new ArcNode(v, w, head)), 
            // the list is in reverse order. We need to reverse it or collect and reverse.
            std::vector<ArcNode*> neighbors;
            ArcNode* currA = _adjList[u];
            while (currA) {
                neighbors.push_back(currA);
                currA = currA->next;
            }
            
            for (int i = neighbors.size() - 1; i >= 0; --i) {
                int v = neighbors[i]->adjVex;
                if (!visited[v]) {
                    visited[v] = true;
                    q.push(v);
                }
            }
        }
        return res;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        os << "Adjacency Table：" << std::endl;
        _vNode* currV = graph._vexList;
        for (int i = 0; i < graph._vexNum; ++i) {
            if (currV) {
                os << i << "\t"; 
                
                std::vector<ArcNode*> order;
                ArcNode* tempA = graph._adjList[i];
                while(tempA) {
                    order.push_back(tempA);
                    tempA = tempA->next;
                }
                
                for (int j = order.size() - 1; j >= 0; --j) {
                    os << order[j]->adjVex << "\t->\t" << order[j]->adjVex << "\t" << order[j]->weight << "\t->\t";
                }
                os << "^" << std::endl;
                currV = currV->next;
            }
        }
        return os;
    }
};

#endif
