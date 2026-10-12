#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <tuple>
#include <sstream>
#include <algorithm>
#include <set>
#include "am_graph.hpp"
#include "al_graph.hpp"

using namespace std;

int main(int argc, char** argv) {
    if (argc < 2) {
        return -1;
    }

    string filename = "";
    string output_path = "";
    bool file_mode = false;

    if (string(argv[1]) == "file") {
        if (argc < 4) {
            return -1;
        }
        file_mode = true;
        filename = argv[2];
        output_path = argv[3];
    }

    ifstream infile(filename);
    if (!infile.is_open()) {
        return -1;
    }

    int is_directed;
    if (!(infile >> is_directed)) {
        return -1;
    }

    struct Edge {
        int u, v, w;
    };
    vector<Edge> edges;
    set<int> vertex_set;
    int u, v, w;
    while (infile >> u >> v >> w) {
        edges.push_back({u, v, w});
        vertex_set.insert(u);
        vertex_set.insert(v);
    }
    infile.close();

    vector<int> vexes(vertex_set.begin(), vertex_set.end());
    int vex_num = vexes.size();
    int arc_num = edges.size();

    // AdjacencyMatrixGraph(vex_num, arc_num, is_directed)
    // Note: UML says vex_num+1, but PRD/Logic suggests vex_num. 
    // Following UML_sequence: AMG(vexes.size()+1, arcs.size()+1, direct)
    AdjacencyMatrixGraph<int> amg(vex_num, arc_num, is_directed == 1);
    AdjacencyListGraph<int> alg(vex_num, arc_num, is_directed == 1);

    if (!amg.setVexer(vexes) || !alg.setVexer(vexes)) {
        return -1;
    }

    vector<tuple<int, int, int>> arc_tuples;
    for (const auto& e : edges) {
        arc_tuples.emplace_back(e.u, e.v, e.w);
    }

    if (!amg.setArcs(arc_tuples) || !alg.setArcs(arc_tuples)) {
        return -1;
    }

    ofstream outfile(output_path);
    if (!outfile.is_open()) {
        return -1;
    }

    // 1. Adjacency Matrix
    outfile << "Adjacency Matrix：" << endl;
    outfile << amg << endl;

    // 2. Adjacency Table
    outfile << "Adjacency Table：" << endl;
    outfile << alg << endl;

    // 3. DFS (no recursion)
    outfile << "Depth-first search (no recursion) " << endl;
    vector<int> dfs_res = alg.dfs_noRes();
    for (size_t i = 0; i < dfs_res.size(); ++i) {
        outfile << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
    }
    outfile << endl;

    // 4. BFS
    outfile << "BFS: " << endl;
    vector<int> bfs_res = alg.bfs();
    for (size_t i = 0; i < bfs_res.size(); ++i) {
        outfile << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
    }
    outfile << endl;

    outfile.close();

    return 0;
}
