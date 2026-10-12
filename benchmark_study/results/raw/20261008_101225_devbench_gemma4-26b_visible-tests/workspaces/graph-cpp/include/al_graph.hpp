#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include <algorithm>
#include <stdexcept>
#include "queue.hpp"
#include "stack.hpp"

template <typename VertexType>
struct ArcNode {
    int adjVex;
    int weight;
    ArcNode<VertexType>* next;
    ArcNode(int adj, int w, ArcNode<VertexType>* n) : adjVex(adj), weight(w), next(n) {}
};

template <typename VertexType>
struct _vNode {
    VertexType v;
    ArcNode<VertexType>* next;
    _vNode() : v(VertexType()), next(nullptr) {}
    _vNode(VertexType val, ArcNode<VertexType>* n) : v(val), next(n) {}
};

template <typename VertexType>
class AdjacencyListGraph {
private:
    bool _isDirected;
    int _vexNum;
    int _arcNum;
    _vNode<VertexType>* _vList;

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum), _vList(nullptr) {
        _vList = new _vNode<VertexType>[_vexNum];
        for (int i = 0; i < _vexNum; ++i) {
            _vList[i].v = VertexType(); // Default init
            _vList[i].next = nullptr;
        }
    }

    // Note: The UML suggests a specific structure. 
    // Since we need to implement setVexes and setArcs as per architecture_design.md
    
    bool setVexes(std::vector<VertexType> vexes) {
        if (vexes.size() != (size_t)_vexNum) throw std::out_of_range("Size mismatch");
        for (int i = 0; i < _vexNum; ++i) {
            _vList[i].v = vexes[i];
        }
        return true;
    }

    bool setArcs(std::vector<std::tuple<VertexType, VertexType, int>> arcs) {
        // Clear existing arcs
        for (int i = 0; i < _vexNum; ++i) {
            ArcNode<VertexType>* curr = _vList[i].next;
            while (curr) {
                ArcNode<VertexType>* temp = curr;
                curr = curr->next;
                delete temp;
            }
            _vList[i].next = nullptr;
        }

        int count = 0;
        for (const auto& arc : arcs) {
            int u = locateVex(std::get<0>(arc));
            int v = locateVex(std::get<1>(arc));
            if (u == -1 || v == -1) return false;

            int w = std::get<2>(arc);
            
            auto pushFrontArc = [&](int from, int to, int weight) {
                ArcNode<VertexType>* newNode = new ArcNode<VertexType>(to, weight, _vList[from].next);
                _vList[from].next = newNode;
            };

            pushFrontArc(u, v, w);
            count++;

            if (!_isDirected) {
                // Add v -> u
                pushFrontArc(v, u, w);
                count++;
            }
        }
        _arcNum = count;
        return true;
    }

    int locateVex(VertexType value) {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vList[i].v == value) return i;
        }
        return -1;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> res;
        if (_vexNum == 0) return res;

        std::vector<bool> visited(_vexNum, false);
        Stack<int> s;

        // Starting from the first vertex (index 0) as per common traversal logic
        s.push(0);

        while (!s.empty()) {
            int currIdx = s.top();
            s.pop();

            if (!visited[currIdx]) {
                visited[currIdx] = true;
                res.push_back(_vList[currIdx].v);

                // To match the expected DFS order, we collect neighbors and push them in reverse order.
                // Since setArcs uses push_front, the list is [last_added, ..., first_added].
                // To visit them in the order they were added (first_added, ..., last_added),
                // we must push them onto the stack in the order they appear in the list.
                // Wait, the requirement says to change from "reverse" to "forward" to make the last neighbor in the list 
                // (which was added last) be at the top of the stack, thus being popped first.
                // Actually, if we want the neighbor with the highest index/last added to be visited first,
                // we push them in the order they appear in the list.
                
                // Let's collect all neighbors in the current list order first.
                std::vector<int> neighbors;
                ArcNode<VertexType>* currArc = _vList[currIdx].next;
                while (currArc) {
                    neighbors.push_back(currArc->adjVex);
                    currArc = currArc->next;
                }
                
                // To have the "first" neighbor in the list (the one added last) be popped first,
                // we push them in the order they appear in the list.
                // But the expected order 1, 2, 4... means 2 is visited before 3.
                // If 1's neighbors are [3, 2] (because 2 was added first, then 3 was push_fronted),
                // and we want 2 to be popped first, we must push 3 then 2.
                // This means we iterate the list and push each neighbor.
                for (int i = neighbors.size() - 1; i >= 0; --i) {
                    s.push(neighbors[i]);
                }
            }
        }
        return res;
    }

    std::vector<VertexType> bfs() {
        return bfs(_vList[0].v);
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
            int currIdx = q.pop();
            res.push_back(_vList[currIdx].v);

            // For BFS, we want to visit neighbors in the order they were added.
            // Since setArcs uses push_front, the list is [last_added, ..., first_added].
            // To visit them in the order they were added, we must traverse the list in reverse.
            std::vector<int> neighbors;
            ArcNode<VertexType>* currArc = _vList[currIdx].next;
            while (currArc) {
                neighbors.push_back(currArc->adjVex);
                currArc = currArc->next;
            }
            for (int i = neighbors.size() - 1; i >= 0; --i) {
                int neighborIdx = neighbors[i];
                if (!visited[neighborIdx]) {
                    visited[neighborIdx] = true;
                    q.push(neighborIdx);
                }
            }
        }
        return res;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& alg) {
        os << "Adjacency Table：" << std::endl;
        for (int i = 0; i < alg._vexNum; ++i) {
            os << alg._vList[i].v << "\t";
            ArcNode<VertexType>* curr = alg._vList[i].next;
            // To print in the order they were added (first_added to last_added),
            // we need to traverse the list in reverse.
            std::vector<std::pair<int, int>> arcList;
            while (curr) {
                arcList.push_back({curr->adjVex, curr->weight});
                curr = curr->next;
            }
            for (int j = arcList.size() - 1; j >= 0; --j) {
                os << arcList[j].first << "\t->\t" << arcList[j].second << "\t";
            }
            os <<"->\t^\t" << std::endl;
        }
        return os;
    }

    ~AdjacencyListGraph() {
        for (int i = 0; i < _vexNum; ++i) {
            ArcNode<VertexType>* curr = _vList[i].next;
            while (curr) {
                ArcNode<VertexType>* temp = curr;
                curr = curr->next;
                delete temp;
            }
        }
        delete[] _vList;
    }
};

#endif
