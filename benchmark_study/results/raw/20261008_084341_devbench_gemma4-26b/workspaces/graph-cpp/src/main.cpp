#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <set>
#include <tuple>
#include <algorithm>
#include "al_graph.hpp"
#include "am_graph.hpp"

using namespace std;

int main(int argc, char** argv) {
    if (argc < 2) {
        return 0;
    }

    string input_file = "";
    string output_file = "";
    bool file_mode = false;

    if (argc == 4 && string(argv[1]) == "file") {
        file_mode = true;
        input_file = argv[2];
        output_file = argv[3];
    }

    bool isDirected = 0;
    vector<int> vexes;
    vector<tuple<int, int, int>> arcs;
    set<int> vertex_set;

    if (file_mode) {
        ifstream ifs(input_file);
        if (!ifs.is_open()) {
            return -1;
        }

        if (!(ifs >> isDirected)) {
            return -1;
        }

        int u, v, w;
        while (ifs >> u >> v >> w) {
            arcs.emplace_back(u, v, w);
            vertex_set.insert(u);
            vertex_set.insert(v);
        }
        ifs.close();
    } else {
        // Default data if no file is provided (though PRD implies file usage)
        // For the purpose of this task, we follow the command line requirement.
        return 0;
    }

    for (int val : vertex_set) {
        vexes.push_back(val);
    }
    // Ensure vexes are sorted if needed, though set handles it
    
    int vexNum = vexes.size();
    int arcNum = arcs.size();

    AdjacencyListGraph<int> alg(vexNum, arcNum, isDirected);
    AdjacencyMatrixGraph<int> amg(vexNum, arcNum, isDirected);

    if (!alg.setVexer(vexes) || !amg.setVexes(vexes)) {
        return -1;
    }

    // Prepare arcs for ALG (needs tuple<VertexType, VertexType, int>)
    vector<tuple<int, int, int>> alg_arcs;
    // Prepare arcs for AMG (needs tuple<int, int, int>)
    vector<tuple<int, int, int>> amg_arcs;

    for (const auto& edge : arcs) {
        alg_arcs.push_back(edge);
        amg_arcs.push_back(edge);
    }

    if (!alg.setArcs(alg_arcs) || !amg.setArcs(amg_arcs)) {
        return -1;
    }

    ofstream ofs(output_file);
    if (!ofs.is_open()) {
        return -1;
    }

    // 1. Adjacency Matrix
    ofs << amg; // Removed extra endl to prevent potential double newline if operator<< adds one

    // 2. Adjacency Table
    ofs << alg; // Removed extra endl to prevent potential double newline if operator<< adds one

    // 3. DFS (no recursion)
    ofs << "Depth-first search (no recursion) " << endl;
    vector<int> dfs_res = alg.dfs_noRes();
    for (size_t i = 0; i < dfs_res.size(); ++i) {
        ofs << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
    }
    ofs << endl;

    // 4. BFS
    ofs << "BFS: " << endl;
    // Assuming BFS starts from the first vertex in the list if not specified
    vector<int> bfs_res = alg.bfs();
    for (size_t i = 0; i < bfs_res.size(); ++i) {
        ofs << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
    }
    ofs << endl;

    ofs.close();

    return 0;
}
