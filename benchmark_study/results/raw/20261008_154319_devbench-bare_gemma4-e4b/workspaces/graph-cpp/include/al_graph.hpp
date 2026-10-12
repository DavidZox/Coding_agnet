#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include <algorithm>
#include <queue>
#include <stack>
#include "queue.hpp"
#include "stack.hpp"

template <typename VertexType>
class AdjacencyListGraph {
private:
    bool _isDirected;
    int _vexNum;
    int _arcNum;

    struct ArcNode {
        int adjVex;
        int weight;
        ArcNode* next;

        ArcNode(int v, int w) : adjVex(v), weight(w), next(nullptr) {}
    };

    // Nested structure for vertex list (as per UML: _vNode)
    struct VNode {
        VertexType v;
        ArcNode* next;

        VNode(const VertexType& val) : v(val), next(nullptr) {}
    };

    // Adjacency list representation: vector of pointers to VNode (head of list for each vertex)
    std::vector<VNode*> _adjList;
    // Vertex mapping: maps VertexType to its index (0 to _vexNum-1)
    std::vector<VertexType> _vexes;

public:
    // Constructor (Implicitly defined or assumed based on usage in sequence diagram)
    AdjacencyListGraph(int numVertices, int numArcs, bool isDirected)
        : _isDirected(isDirected), _vexNum(numVertices), _arcNum(numArcs) {
        _adjList.resize(_vexNum, nullptr);
    }

    // Destructor to clean up memory
    ~AdjacencyListGraph() {
        for (int i = 0; i < _vexNum; ++i) {
            ArcNode* currentArc = _adjList[i];
            while (currentArc != nullptr) {
                ArcNode* toDelete = currentArc;
                currentArc = currentArc->next;
                delete toDelete;
            }
        }
        // Note: VNode cleanup is implicitly handled if we assume _vexes holds the actual vertex objects,
        // but since the UML suggests _vNode contains the vertex data, we rely on the structure setup.
        // For simplicity matching the provided structure, we focus on ArcNode cleanup.
    }

    // Sets the vertex list and returns success status
    bool setVexes(const std::vector<VertexType>& vexes) {
        if (vexes.size() != _vexNum) {
            return false;
        }
        _vexes = vexes;
        // Reinitialize adjacency list pointers to null
        for (int i = 0; i < _vexNum; ++i) {
            _adjList[i] = nullptr;
        }
        return true;
    }

    // Sets the arcs and returns success status
    // Arc format: {start_vertex, end_vertex, weight}
    bool setArcs(const std::vector<std::tuple<VertexType, VertexType, int>>& arcs) {
        if (arcs.size() != _arcNum) {
            return false;
        }

        // Clear existing arcs first
        for (int i = 0; i < _vexNum; ++i) {
            ArcNode* currentArc = _adjList[i];
            while (currentArc != nullptr) {
                ArcNode* toDelete = currentArc;
                currentArc = currentArc->next;
                delete toDelete;
            }
            _adjList[i] = nullptr;
        }

        for (const auto& arc : arcs) {
            VertexType u_val = std::get<0>(arc);
            VertexType v_val = std::get<1>(arc);
            int weight = std::get<2>(arc);

            int u_idx = locateVex(u_val);
            int v_idx = locateVex(v_val);

            if (u_idx == -1 || v_idx == -1) {
                return false; // Vertex not found
            }

            // Create new arc node
            ArcNode* newArc = new ArcNode(v_idx, weight);

            // Insert at the head of the adjacency list for u_idx
            newArc->next = _adjList[u_idx];
            _adjList[u_idx] = newArc;

            // If undirected, add the reverse edge
            if (!_isDirected) {
                ArcNode* reverseArc = new ArcNode(u_idx, weight);
                reverseArc->next = _adjList[v_idx];
                _adjList[v_idx] = reverseArc;
            }
        }
        return true;
    }

    // Finds the index (0 to _vexNum-1) corresponding to a VertexType value
    int locateVex(const VertexType& value) const {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexes[i] == value) {
                return i;
            }
        }
        return -1; // Not found
    }

    // Output operator for Adjacency List Graph
    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph<VertexType>& graph) {
        // This operator is primarily used for printing the structure, though the PRD focuses on matrix/table output.
        // We implement a basic representation here.
        os << "Adjacency List Graph (Directed: " << (graph._isDirected ? "Yes" : "No") << ", Vertices: " << graph._vexNum << ")";
        return os;
    }

    // Non-recursive Depth-First Traversal
    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> result;
        if (_vexNum == 0) return result;

        std::vector<bool> visited(_vexNum, false);
        std::stack<int> s;

        // Start from the first vertex (index 0)
        s.push(0);
        visited[0] = true;

        while (!s.empty()) {
            int u_idx = s.top();
            s.pop();

            // Add vertex to result sequence
            result.push_back(_vexes[u_idx]);

            // Traverse neighbors (in reverse order to mimic standard DFS behavior if needed,
            // but here we just iterate through the list)
            ArcNode* currentArc = _adjList[u_idx];
            std::vector<int> neighbors;
            while (currentArc) {
                int v_idx = currentArc->adjVex;
                neighbors.push_back(v_idx);
                currentArc = currentArc->next;
            }
            
            // Push unvisited neighbors onto the stack (reverse order ensures smaller index is processed first if multiple neighbors exist)
            std::reverse(neighbors.begin(), neighbors.end());
            for (int v_idx : neighbors) {
                if (!visited[v_idx]) {
                    visited[v_idx] = true;
                    s.push(v_idx);
                }
            }
        }
        return result;
    }

    // Breadth-First Traversal (General, starting from index 0 if not specified)
    std::vector<VertexType> bfs() {
        return bfs(0);
    }

    // Breadth-First Traversal (Starting from a specific vertex index)
    std::vector<VertexType> bfs(int start_index) {
        std::vector<VertexType> result;
        if (_vexNum == 0) return result;

        std::vector<bool> visited(_vexNum, false);
        Queue<int> q;

        q.push(start_index);
        visited[start_index] = true;

        while (!q.empty()) {
            int u_idx = q.front();
            q.pop();

            // Add vertex to result sequence
            result.push_back(_vexes[u_idx]);

            // Traverse neighbors
            ArcNode* currentArc = _adjList[u_idx];
            std::vector<int> neighbors;
            while (currentArc) {
                int v_idx = currentArc->adjVex;
                neighbors.push_back(v_idx);
                currentArc = currentArc->next;
            }

            // Push unvisited neighbors onto the queue
            for (int v_idx : neighbors) {
                if (!visited[v_idx]) {
                    visited[v_idx] = true;
                    q.push(v_idx);
                }
            }
        }
        return result;
    }
};

#endif // AL_GRAPH_HPP
