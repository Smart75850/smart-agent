package api

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
)

// 平台名必须为合法标识符，防止路径穿越（../、%2F、反斜杠等一律拒绝）
var platformNameRe = regexp.MustCompile(`^[a-z0-9_]{1,32}$`)

func (s *Server) handleDataPlatform(w http.ResponseWriter, r *http.Request) {
	platform := r.PathValue("platform")
	if !platformNameRe.MatchString(platform) {
		writeJSON(w, http.StatusOK, map[string]any{"platform": platform, "items": []any{}, "message": "no data"})
		return
	}

	files, err := filepath.Glob(filepath.Join("output", platform+"_*.json"))
	if err != nil || len(files) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"platform": platform, "items": []any{}, "message": "no data"})
		return
	}

	latest := files[len(files)-1]
	data, err := os.ReadFile(latest)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "read file failed")
		return
	}

	var result any
	json.Unmarshal(data, &result)
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) handleDataList(w http.ResponseWriter, r *http.Request) {
	entries, _ := os.ReadDir("output")
	platforms := make(map[string]int)
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		for _, p := range []string{"bilibili", "douyin", "kuaishou", "xiaohongshu", "zhihu", "weibo", "tieba"} {
			if _, ok := platforms[p]; !ok {
				platforms[p] = 0
			}
		}
	}
	for _, e := range entries {
		for _, p := range []string{"bilibili", "douyin", "kuaishou", "xiaohongshu", "zhihu", "weibo", "tieba"} {
			if len(e.Name()) > len(p) && e.Name()[:len(p)] == p {
				platforms[p]++
			}
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"platforms": platforms})
}
