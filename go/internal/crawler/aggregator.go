package crawler

import (
	"crypto/md5"
	"fmt"
	"sort"
	"strconv"
	"strings"

	"github.com/Smart75850/smart-agent-pro/go/pkg/models"
)

// MergeAndDedup 合并多平台结果，三路去重 (link, platform_id, title-md5)，按播放量排序。
func MergeAndDedup(platformResults map[string][]models.Item) []models.Item {
	var all []models.Item
	for platform, items := range platformResults {
		for i := range items {
			items[i].Platform = platform
		}
		all = append(all, items...)
	}

	seenLink := make(map[string]bool)
	seenID := make(map[string]bool)
	seenTitle := make(map[string]bool)

	var deduped []models.Item
	for _, it := range all {
		if it.Link != "" && seenLink[it.Link] {
			continue
		}
		if it.PlatformID != "" && seenID[it.PlatformID] {
			continue
		}
		titleHash := titleHash(it.Title)
		if titleHash != "" && seenTitle[titleHash] {
			continue
		}

		if it.Link != "" {
			seenLink[it.Link] = true
		}
		if it.PlatformID != "" {
			seenID[it.PlatformID] = true
		}
		if titleHash != "" {
			seenTitle[titleHash] = true
		}
		deduped = append(deduped, it)
	}

	sort.Slice(deduped, func(i, j int) bool {
		return parsePlays(deduped[i].Plays) > parsePlays(deduped[j].Plays)
	})

	return deduped
}

func titleHash(title string) string {
	t := strings.TrimSpace(title)
	if len(t) < 4 {
		return ""
	}
	return fmt.Sprintf("%x", md5.Sum([]byte(t)))
}

func parsePlays(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	// 处理中文单位: 1.2万 -> 12000, 3.5亿 -> 350000000
	if strings.HasSuffix(s, "亿") {
		v, err := strconv.ParseFloat(strings.TrimSuffix(s, "亿"), 64)
		if err == nil {
			return int(v * 1e8)
		}
	}
	if strings.HasSuffix(s, "万") {
		v, err := strconv.ParseFloat(strings.TrimSuffix(s, "万"), 64)
		if err == nil {
			return int(v * 1e4)
		}
	}
	// 处理逗号分隔: 1,234,567
	s = strings.ReplaceAll(s, ",", "")
	v, err := strconv.Atoi(s)
	if err != nil {
		return 0
	}
	return v
}
