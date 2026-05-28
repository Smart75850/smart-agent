package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"

	"github.com/Smart75850/smart-agent-pro/go/internal/api"
	"github.com/Smart75850/smart-agent-pro/go/internal/config"
	"github.com/Smart75850/smart-agent-pro/go/internal/orchestrator"
	"github.com/Smart75850/smart-agent-pro/go/pkg/models"
)

func main() {
	serve := flag.Bool("serve", false, "启动 API 服务器")
	keyword := flag.String("keyword", "", "搜索关键词")
	platform := flag.String("platform", "", "指定平台 (bilibili/douyin/kuaishou/xiaohongshu/zhihu/weibo/tieba)，留空=全平台")
	pipelineMode := flag.String("pipeline", "full", "管道模式: simple|full")
	limit := flag.Int("limit", 10, "每平台搜索条数")
	flag.Parse()

	cfg := config.Load()

	if *serve {
		runServer(cfg)
		return
	}

	if *keyword == "" {
		fmt.Println("用法:")
		fmt.Println("  smart-agent --serve                 启动 API 服务器")
		fmt.Println("  smart-agent --keyword <关键词>       运行 pipeline (全平台)")
		fmt.Println("  smart-agent --keyword <关键词> --platform bilibili  指定平台")
		fmt.Println("  smart-agent --keyword <关键词> --pipeline simple  仅搜索+聚合")
		fmt.Println("  smart-agent --keyword <关键词> --limit 20          指定数量")
		os.Exit(1)
	}

	platforms := []string{"bilibili", "douyin", "kuaishou", "xiaohongshu", "zhihu", "weibo", "tieba"}
	if *platform != "" {
		platforms = []string{*platform}
	}

	runCLI(*keyword, *pipelineMode, *limit, platforms)
}

func runServer(cfg *config.Settings) {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	server := api.NewServer(cfg)
	log.Printf("Smart Agent Pro (Go) — API 服务器 :%s", cfg.APIPort)
	log.Printf("Sidecar: %s", cfg.SidecarURL)
	if err := server.Start(ctx); err != nil {
		log.Fatalf("服务器退出: %v", err)
	}
}

func runCLI(keyword, mode string, limit int, platforms []string) {
	state := &models.PipelineState{
		Keyword:      keyword,
		Platforms:    platforms,
		Limit:        limit,
		PipelineMode: mode,
	}

	graph := orchestrator.NewGraph(mode)
	ctx := context.Background()

	result, err := graph.Run(ctx, state)
	if err != nil {
		log.Fatalf("Pipeline 失败: %v", err)
	}

	fmt.Println()
	fmt.Println("========================================")
	fmt.Printf("  关键词: %s\n", result.Keyword)
	fmt.Printf("  模式:   %s\n", result.PipelineMode)
	fmt.Printf("  平台:   %v\n", result.Platforms)
	fmt.Printf("  结果:   %d 条\n", result.TotalItems)
	fmt.Println("========================================")

	if mode == "full" && result.Reports != nil {
		for name, report := range result.Reports {
			fmt.Printf("  [%s] %v\n", name, report != nil)
		}
	}
}
