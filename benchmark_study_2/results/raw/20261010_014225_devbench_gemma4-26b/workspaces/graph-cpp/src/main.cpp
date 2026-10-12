#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <tuple>
#include <algorithm>
#include <set>
#include "am_graph.hpp"
#include "al_graph.hpp"

using namespace std;

int main(int argc, char** argv) {
    if (argc < 2) {
        cerr << "Error: Not enough arguments." << endl;
        return -1;
    }

    string filename = "";
    string output_path = "";
    bool file_mode = false;

    if (argc == 4 && string(argv[1]) == "file") {
        file_mode = true;
        filename = argv[2];
        output_path = argv[3];
    } else if (argc == 2) {
        filename = argv[1];
    } else {
        cerr << "Error: Invalid command line arguments." << endl;
        return -1;
    }

    ifstream infile(filename);
    if (!infile.is_open()) {
        cerr << "Error: Could not open input file: " << filename << endl;
        return -1;
    }

    int isDirected;
    if (!(infile >> isDirected)) {
        cerr << "Error: Failed to read directed/undirected flag." << endl;
        return -1;
    }

    vector<tuple<int, int, int>> arcs_raw;
    set<int> vertex_set;
    int u, v, w;
    while (infile >> u >> v >> w) {
        arcs_raw.emplace_back(u, v, w);
        vertex_set.insert(u);
        vertex_set.insert(v);
    }
    infile.close();

    int max_v = -1;
    for (int val : vertex_set) {
        if (val > max_v) max_v = val;
    }
    
    vector<int> vexes;
    if (max_v >= 0) {
        for (int i = 0; i <= max_v; ++i) {
            vexes.push_back(i);
        }
    }

    int vexNum = vexes.size();
    int arcNum = arcs_raw.size();

    AdjacencyMatrixGraph<int> amg(vexNum, arcNum, isDirected == 1);
    AdjacencyListGraph<int> alg(vexNum, arcNum, isDirected == 1);

    if (vexNum > 0) {
        if (!amg.setVexes(vexes)) {
            cerr << "Error: AMG setVexes failed." << endl;
            return -1;
        }
        if (!alg.setVexes(vexes)) {
            cerr << "Error: ALG setVexes failed." << endl;
            return -1;
        }
    }

    vector<tuple<int, int, int>> amg_arcs;
    for (const auto& arc : arcs_raw) {
        int start_val = get<0>(arc);
        int end_val = get<1>(arc);
        int weight = get<2>(arc);
        
        int start_idx = amg.locateVex(start_val);
        int end_idx = amg.locateVex(end_val);
        
        if (start_idx != -1 && end_idx != -1) {
            amg_arcs.emplace_back(start_idx, end_idx, weight);
        }
    }

    if (vexNum > 0 && !amg_arcs.empty()) {
        if (!amg.setArcs(amg_arcs)) {
            cerr << "Error: AMG setArcs failed." << endl;
            return -1;
        }
    }
    
    if (vexNum > 0 && !arcs_raw.empty()) {
        if (!alg.setArcs(arcs_raw)) {
            cerr << "Error: ALG setArcs failed." << endl;
            return -1;
        }
    }

    ostream* out = &cout;
    ofstream outfile;
    if (file_mode && !output_path.empty()) {
        outfile.open(output_path);
        if (outfile.is_open()) {
            out = &outfile;
        } else {
            cerr << "Error: Could not open output file: " << output_path << endl;
            return -1;
        }
    }

    *out << amg;
    *out << alg;

    vector<int> dfs_res = alg.dfs_noRes();
    *out << "Depth-first search (no recursion) \n";
    if (!dfs_res.empty()) {
        for (size_t i = 0; i < dfs_res.size(); ++i) {
            *out << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
        }
        *out << "\n";
    }

    vector<int> bfs_res = alg.bfs();
    *out << "BFS: \n";
    if (!bfs_res.empty()) {
        for (size_t i = 0; i < bfs_res.size(); ++i) {
            *out << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
        }
        *out << "\n";
    }

    if (outfile.is_open()) {
        outfile.close();
    }

    return 0;
}
