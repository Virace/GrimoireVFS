<#
.SYNOPSIS
    GrimoireVFS 版本发布工具

.DESCRIPTION
    交互式版本发布脚本，支持:
    - 选择版本类型 (dev/patch/minor/major)
    - 自动更新版本号
    - 创建 git commit 和 tag
    - 推送到远程仓库

.PARAMETER DryRun
    模拟模式，不执行任何实际操作

.EXAMPLE
    .\scripts\release.ps1
    .\scripts\release.ps1 -DryRun
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# ============================================================
# 工具函数
# ============================================================

function Write-Title {
    param([string]$Text)
    Write-Host ("=" * 50) -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 50) -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Text)
    if ($DryRun) {
        Write-Host "[模拟] $Text" -ForegroundColor Yellow
    } else {
        Write-Host $Text -ForegroundColor Green
    }
}

function Invoke-Command-Safe {
    param(
        [string]$Command,
        [switch]$Capture,
        [switch]$AllowFailure
    )
    
    if ($DryRun -and -not $Capture) {
        Write-Host "  > $Command" -ForegroundColor DarkGray
        return ""
    }
    
    if ($Capture) {
        $result = Invoke-Expression $Command 2>&1
        if ($LASTEXITCODE -ne 0 -and -not $AllowFailure) {
            Write-Host "❌ 命令执行失败: $Command" -ForegroundColor Red
            Write-Host $result -ForegroundColor Red
            exit 1
        }
        return $result
    } else {
        Invoke-Expression $Command
        if ($LASTEXITCODE -ne 0 -and -not $AllowFailure) {
            Write-Host "❌ 命令执行失败: $Command" -ForegroundColor Red
            exit 1
        }
    }
}

function Get-CurrentVersion {
    $version = Invoke-Command-Safe "uv version --short" -Capture
    return $version.Trim()
}

function Test-IsPrerelease {
    param([string]$Version)
    return $Version -match "(dev|alpha|beta|a\d|b\d|rc)"
}

function Convert-VersionToTag {
    param([string]$Version)
    # 0.2.0.dev1 -> v0.2.0-dev1
    $tag = $Version -replace "\.dev", "-dev"
    return "v$tag"
}

function Update-Version {
    param([string]$BumpType)
    
    $current = Get-CurrentVersion
    $isDevVersion = Test-IsPrerelease $current
    
    Write-Step "📝 更新版本号..."
    
    if ($BumpType -eq "dev") {
        if ($isDevVersion) {
            # 已经是 dev 版本，只递增 dev 号
            Invoke-Command-Safe "uv version --bump dev --no-sync"
        } else {
            # 稳定版，递增 patch 并加 dev
            Invoke-Command-Safe "uv version --bump patch --bump dev --no-sync"
        }
    } else {
        # patch/minor/major
        if ($isDevVersion) {
            # 预发布版本，升级为稳定版
            Invoke-Command-Safe "uv version --bump stable --no-sync"
        } else {
            # 稳定版，递增指定版本
            Invoke-Command-Safe "uv version --bump $BumpType --no-sync"
        }
    }
    
    if ($DryRun) {
        # 模拟模式下预测新版本
        if ($BumpType -eq "dev") {
            if ($isDevVersion) {
                # 0.1.1.dev1 -> 0.1.1.dev2
                if ($current -match "\.dev(\d+)$") {
                    $devNum = [int]$Matches[1] + 1
                    return $current -replace "\.dev\d+$", ".dev$devNum"
                }
            } else {
                # 0.1.0 -> 0.1.1.dev1
                $parts = $current -split "\."
                $parts[2] = [int]$parts[2] + 1
                return "$($parts -join '.').dev1"
            }
        } elseif ($BumpType -eq "patch") {
            if ($isDevVersion) {
                return $current -replace "\.dev\d+$", ""
            }
            $parts = $current -split "\."
            $parts[2] = [int]$parts[2] + 1
            return $parts -join "."
        } elseif ($BumpType -eq "minor") {
            if ($isDevVersion) {
                return $current -replace "\.dev\d+$", ""
            }
            $parts = $current -split "\."
            $parts[1] = [int]$parts[1] + 1
            $parts[2] = 0
            return $parts -join "."
        } elseif ($BumpType -eq "major") {
            if ($isDevVersion) {
                return $current -replace "\.dev\d+$", ""
            }
            $parts = $current -split "\."
            $parts[0] = [int]$parts[0] + 1
            $parts[1] = 0
            $parts[2] = 0
            return $parts -join "."
        }
        return $current
    }
    
    return Get-CurrentVersion
}

function New-GitCommitAndTag {
    param(
        [string]$Version,
        [string]$Tag
    )
    
    Write-Step "📝 创建 Git commit..."
    Invoke-Command-Safe "git add pyproject.toml uv.lock"
    
    if (Test-IsPrerelease $Version) {
        $msg = "chore: bump version to $Version"
    } else {
        $msg = "chore: release $Version"
    }
    
    Invoke-Command-Safe "git commit -m `"$msg`""
    Write-Host "✅ 已创建 commit: $msg" -ForegroundColor Green
    
    Write-Step "🏷️ 创建 Git tag..."
    Invoke-Command-Safe "git tag $Tag"
    Write-Host "✅ 已创建 tag: $Tag" -ForegroundColor Green
}

function Push-ToRemote {
    Write-Step "📤 推送到远程仓库..."
    Invoke-Command-Safe "git push"
    Invoke-Command-Safe "git push --tags"
    Write-Host "✅ 推送完成!" -ForegroundColor Green
}

function Restore-Version {
    param([string]$OriginalVersion)
    
    if (-not $DryRun) {
        Write-Host "⏪ 回滚版本..." -ForegroundColor Yellow
        Invoke-Command-Safe "uv version $OriginalVersion --no-sync"
    }
}

# ============================================================
# 主流程
# ============================================================

Write-Title "🚀 GrimoireVFS 版本发布工具"

if ($DryRun) {
    Write-Host "`n⚠️  模拟模式 - 不会执行任何实际操作`n" -ForegroundColor Yellow
}

$currentVersion = Get-CurrentVersion
Write-Host "`n📦 当前版本: $currentVersion" -ForegroundColor White

# 显示选项
Write-Host "`n请选择版本类型:" -ForegroundColor White
Write-Host "  1. dev   - 开发版迭代" -ForegroundColor Gray
Write-Host "  2. patch - 小修复" -ForegroundColor Gray
Write-Host "  3. minor - 新功能" -ForegroundColor Gray
Write-Host "  4. major - 大版本" -ForegroundColor Gray
Write-Host "  0. 取消" -ForegroundColor Gray
Write-Host "`n  所有版本都会先发布到 Test-PyPI，正式发布需手动创建 GitHub Release" -ForegroundColor DarkGray

$choice = Read-Host "`n请输入选项 [0-4]"

$bumpMap = @{
    "1" = "dev"
    "2" = "patch"
    "3" = "minor"
    "4" = "major"
}

if ($choice -eq "0" -or $choice -eq "") {
    Write-Host "已取消" -ForegroundColor Yellow
    exit 0
}

if (-not $bumpMap.ContainsKey($choice)) {
    Write-Host "❌ 无效的选项" -ForegroundColor Red
    exit 1
}

$bumpType = $bumpMap[$choice]

# 执行版本递增
$newVersion = Update-Version $bumpType
$tag = Convert-VersionToTag $newVersion
$isPrerelease = Test-IsPrerelease $newVersion

Write-Host "`n📦 新版本: $newVersion" -ForegroundColor Cyan
Write-Host "🏷️  Tag: $tag" -ForegroundColor Cyan

Write-Host "📤 目标: Test-PyPI" -ForegroundColor Cyan
if (-not $isPrerelease) {
    Write-Host "   (正式版需手动创建 GitHub Release 发布到 PyPI)" -ForegroundColor DarkGray
}

# 确认
$confirm = Read-Host "`n确认发布? [y/N]"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Restore-Version $currentVersion
    Write-Host "已取消" -ForegroundColor Yellow
    exit 0
}

# 执行发布流程
Write-Host ""
Write-Title "执行发布流程"

New-GitCommitAndTag $newVersion $tag
Push-ToRemote

Write-Host ""
Write-Title "发布完成"

Write-Host "🎉 版本已推送! GitHub Actions 将自动发布到 Test-PyPI" -ForegroundColor Green
Write-Host "   pip install -i https://test.pypi.org/simple/ grimoirevfs==$newVersion" -ForegroundColor White
if (-not $isPrerelease) {
    Write-Host "`n📋 正式版发布步骤:" -ForegroundColor Yellow
    Write-Host "   1. 在 Test-PyPI 测试安装验证" -ForegroundColor White
    Write-Host "   2. 创建 GitHub Release: https://github.com/Virace/GrimoireVFS/releases/new?tag=$tag" -ForegroundColor White
}
