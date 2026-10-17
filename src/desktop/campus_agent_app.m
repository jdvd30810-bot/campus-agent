//
//  campus_agent_app.m
//  Campus-Agent Native macOS Desktop Client (Cocoa + WebKit)
//
//  Created for Campus-Agent (校园群聊智能降噪与 DDL 预警助手)
//

#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>

@interface CampusAgentAppDelegate : NSObject <NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate>

@property (strong, nonatomic) NSWindow *window;
@property (strong, nonatomic) WKWebView *webView;
@property (strong, nonatomic) NSView *splashView;
@property (strong, nonatomic) NSProgressIndicator *spinner;
@property (strong, nonatomic) NSTextField *statusLabel;

@property (strong, nonatomic) NSString *serverUrl;
@property (strong, nonatomic) NSString *projectRoot;
@property (strong, nonatomic) NSTimer *healthCheckTimer;
@property (assign, nonatomic) NSInteger retryCount;
@property (assign, nonatomic) BOOL isServerRunning;

@end

@implementation CampusAgentAppDelegate

- (instancetype)init {
    self = [super init];
    if (self) {
        _serverUrl = @"http://127.0.0.1:8000";
        _retryCount = 0;
        _isServerRunning = NO;
        _projectRoot = [self detectProjectRoot];
    }
    return self;
}

- (NSString *)detectProjectRoot {
    // 1. 优先使用环境变量 CAMPUS_AGENT_ROOT
    char *envRoot = getenv("CAMPUS_AGENT_ROOT");
    if (envRoot && strlen(envRoot) > 0) {
        return [NSString stringWithUTF8String:envRoot];
    }
    
    // 2. 检查 App Bundle 所在层级 (如果在 bin/CampusAgent.app，则父目录的父目录是工程根目录)
    NSString *bundlePath = [[NSBundle mainBundle] bundlePath];
    NSString *parentDir = [bundlePath stringByDeletingLastPathComponent];
    NSString *grandParentDir = [parentDir stringByDeletingLastPathComponent];
    
    NSFileManager *fm = [NSFileManager defaultManager];
    if ([fm fileExistsAtPath:[grandParentDir stringByAppendingPathComponent:@"app/main.py"]]) {
        return grandParentDir;
    }
    if ([fm fileExistsAtPath:[parentDir stringByAppendingPathComponent:@"app/main.py"]]) {
        return parentDir;
    }
    
    // 3. 检查当前工作路径
    NSString *cwd = [fm currentDirectoryPath];
    if ([fm fileExistsAtPath:[cwd stringByAppendingPathComponent:@"app/main.py"]]) {
        return cwd;
    }
    
    // 4. 兜底默认路径
    return @"/Users/kangyuchou/.gemini/antigravity/scratch/campus-agent";
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    // 1. 设置为标准 GUI 桌面应用程序 (在 macOS Dock 栏显示独立图标)
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    
    // 2. 加载并设置 Dock 图标
    NSString *iconPath = [[NSBundle mainBundle] pathForResource:@"AppIcon" ofType:@"icns"];
    if (iconPath) {
        NSImage *icon = [[NSImage alloc] initWithContentsOfFile:iconPath];
        if (icon) {
            [NSApp setApplicationIconImage:icon];
        }
    }
    
    // 3. 构建原生 macOS 系统菜单栏
    [self setupMainMenu];
    
    // 4. 构建主窗口 (现代 macOS 毛玻璃视窗)
    [self setupMainWindow];
    
    // 5. 启动自检与后端唤醒
    [self startHealthCheckAndLaunch];
    
    // 6. 前置并激活本应用
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)setupMainWindow {
    NSRect screenRect = [[NSScreen mainScreen] visibleFrame];
    CGFloat winWidth = 1260;
    CGFloat winHeight = 840;
    NSRect winRect = NSMakeRect((screenRect.size.width - winWidth) / 2 + screenRect.origin.x,
                                (screenRect.size.height - winHeight) / 2 + screenRect.origin.y,
                                winWidth, winHeight);
    
    NSWindowStyleMask style = NSWindowStyleMaskTitled |
                              NSWindowStyleMaskClosable |
                              NSWindowStyleMaskMiniaturizable |
                              NSWindowStyleMaskResizable |
                              NSWindowStyleMaskFullSizeContentView;
    
    self.window = [[NSWindow alloc] initWithContentRect:winRect
                                              styleMask:style
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    self.window.title = @"Campus-Agent | 校园消息智能助手";
    self.window.titlebarAppearsTransparent = YES;
    self.window.titleVisibility = NSWindowTitleHidden;
    self.window.minSize = NSMakeSize(960, 600);
    self.window.delegate = self;
    self.window.backgroundColor = [NSColor windowBackgroundColor];
    
    NSView *contentView = self.window.contentView;
    
    // 初始化现代 WebKit 视图
    WKWebViewConfiguration *config = [[WKWebViewConfiguration alloc] init];
    config.preferences.javaScriptCanOpenWindowsAutomatically = YES;
    
    self.webView = [[WKWebView alloc] initWithFrame:contentView.bounds configuration:config];
    self.webView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    self.webView.navigationDelegate = self;
    self.webView.UIDelegate = self;
    self.webView.hidden = YES; // 等待加载就绪后再显现
    [contentView addSubview:self.webView];
    
    // 初始化优雅的原生启动过渡视图 (Splash View)
    [self setupSplashView];
    
    [self.window makeKeyAndOrderFront:nil];
}

- (void)setupSplashView {
    NSView *contentView = self.window.contentView;
    self.splashView = [[NSView alloc] initWithFrame:contentView.bounds];
    self.splashView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    
    // 居中卡片容器
    CGFloat cardW = 380;
    CGFloat cardH = 340;
    NSRect cardRect = NSMakeRect((contentView.bounds.size.width - cardW) / 2,
                                 (contentView.bounds.size.height - cardH) / 2 + 30,
                                 cardW, cardH);
    NSView *card = [[NSView alloc] initWithFrame:cardRect];
    card.autoresizingMask = NSViewMinXMargin | NSViewMaxXMargin | NSViewMinYMargin | NSViewMaxYMargin;
    
    // 奶蛙 Logo 图标
    NSString *logoPath = [[NSBundle mainBundle] pathForResource:@"naiwa_logo" ofType:@"png"];
    if (!logoPath) {
        logoPath = [self.projectRoot stringByAppendingPathComponent:@"app/static/naiwa_sticker.png"];
    }
    NSImage *logoImg = [[NSImage alloc] initWithContentsOfFile:logoPath];
    NSImageView *logoView = [[NSImageView alloc] initWithFrame:NSMakeRect((cardW - 140) / 2, cardH - 150, 140, 140)];
    logoView.image = logoImg;
    logoView.imageScaling = NSImageScaleProportionallyUpOrDown;
    [card addSubview:logoView];
    
    // 标题文本
    NSTextField *titleLabel = [[NSTextField alloc] initWithFrame:NSMakeRect(0, cardH - 200, cardW, 32)];
    titleLabel.stringValue = @"Campus-Agent";
    titleLabel.font = [NSFont systemFontOfSize:24 weight:NSFontWeightBold];
    titleLabel.alignment = NSTextAlignmentCenter;
    titleLabel.bordered = NO;
    titleLabel.editable = NO;
    titleLabel.drawsBackground = NO;
    [card addSubview:titleLabel];
    
    // 状态文本
    self.statusLabel = [[NSTextField alloc] initWithFrame:NSMakeRect(0, cardH - 235, cardW, 22)];
    self.statusLabel.stringValue = @"正在唤醒智能学伴与守护核心...";
    self.statusLabel.font = [NSFont systemFontOfSize:13 weight:NSFontWeightMedium];
    self.statusLabel.textColor = [NSColor secondaryLabelColor];
    self.statusLabel.alignment = NSTextAlignmentCenter;
    self.statusLabel.bordered = NO;
    self.statusLabel.editable = NO;
    self.statusLabel.drawsBackground = NO;
    [card addSubview:self.statusLabel];
    
    // 进度旋转器
    self.spinner = [[NSProgressIndicator alloc] initWithFrame:NSMakeRect((cardW - 32) / 2, cardH - 285, 32, 32)];
    self.spinner.style = NSProgressIndicatorStyleSpinning;
    self.spinner.controlSize = NSControlSizeRegular;
    [self.spinner startAnimation:nil];
    [card addSubview:self.spinner];
    
    [self.splashView addSubview:card];
    [contentView addSubview:self.splashView];
}

- (void)startHealthCheckAndLaunch {
    [self checkBackendHealth];
    
    // 每 400ms 检测一次后台服务
    self.healthCheckTimer = [NSTimer scheduledTimerWithTimeInterval:0.4
                                                             target:self
                                                           selector:@selector(checkBackendHealth)
                                                           userInfo:nil
                                                            repeats:YES];
}

- (void)checkBackendHealth {
    NSURL *url = [NSURL URLWithString:[self.serverUrl stringByAppendingString:@"/api/v1/daemon/status"]];
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:url
                                                       cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                   timeoutInterval:0.8];
    req.HTTPMethod = @"GET";
    
    [[[NSURLSession sharedSession] dataTaskWithRequest:req
                                     completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        NSHTTPURLResponse *httpResp = (NSHTTPURLResponse *)response;
        if (!error && httpResp.statusCode == 200) {
            dispatch_async(dispatch_get_main_queue(), ^{
                [self onBackendReady];
            });
        } else {
            dispatch_async(dispatch_get_main_queue(), ^{
                self.retryCount++;
                if (self.retryCount == 2 && !self.isServerRunning) {
                    // 服务未就绪，自动唤起后台 Python 服务
                    [self launchBackendProcess];
                }
                if (self.retryCount > 25) {
                    self.statusLabel.stringValue = @"连接超时，请检查后重新启动或在终端执行 ./start_server.sh";
                    [self.spinner stopAnimation:nil];
                }
            });
        }
    }] resume];
}

- (void)launchBackendProcess {
    self.isServerRunning = YES;
    self.statusLabel.stringValue = @"正在为您启动本地 FastAPI 智能网关...";
    
    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
        NSString *startScript = [self.projectRoot stringByAppendingPathComponent:@"start_server.sh"];
        NSFileManager *fm = [NSFileManager defaultManager];
        
        if ([fm fileExistsAtPath:startScript]) {
            NSTask *task = [[NSTask alloc] init];
            task.launchPath = @"/bin/bash";
            task.arguments = @[startScript];
            task.currentDirectoryPath = self.projectRoot;
            
            @try {
                [task launch];
                [task waitUntilExit];
            } @catch (NSException *ex) {
                NSLog(@"启动脚本调用失败: %@", ex);
            }
        } else {
            // 如果脚本不存在，尝试直接调用虚拟环境 python
            NSString *pythonBin = [self.projectRoot stringByAppendingPathComponent:@"venv/bin/python"];
            if ([fm fileExistsAtPath:pythonBin]) {
                NSTask *task = [[NSTask alloc] init];
                task.launchPath = pythonBin;
                task.arguments = @[@"-m", @"uvicorn", @"app.main:app", @"--host", @"0.0.0.0", @"--port", @"8000"];
                task.currentDirectoryPath = self.projectRoot;
                @try {
                    [task launch];
                } @catch (NSException *ex) {
                    NSLog(@"直接调用 uvicorn 异常: %@", ex);
                }
            }
        }
    });
}

- (void)onBackendReady {
    if (self.healthCheckTimer) {
        [self.healthCheckTimer invalidate];
        self.healthCheckTimer = nil;
    }
    
    self.statusLabel.stringValue = @"内核连接成功，正在载入控制台...";
    
    // 加载控制台页面
    NSURL *dashboardUrl = [NSURL URLWithString:[self.serverUrl stringByAppendingString:@"/dashboard"]];
    [self.webView loadRequest:[NSURLRequest requestWithURL:dashboardUrl]];
    
    // 平滑淡入
    [NSAnimationContext runAnimationGroup:^(NSAnimationContext *context) {
        context.duration = 0.35;
        self.splashView.animator.alphaValue = 0.0;
    } completionHandler:^{
        [self.splashView removeFromSuperview];
        self.webView.hidden = NO;
        self.webView.alphaValue = 0.0;
        [NSAnimationContext runAnimationGroup:^(NSAnimationContext *ctx) {
            ctx.duration = 0.25;
            self.webView.animator.alphaValue = 1.0;
        }];
    }];
}

#pragma mark - 菜单栏设置

- (void)setupMainMenu {
    NSMenu *mainMenu = [[NSMenu alloc] init];
    
    // 1. App 菜单
    NSMenuItem *appMenuItem = [[NSMenuItem alloc] init];
    NSMenu *appMenu = [[NSMenu alloc] initWithTitle:@"Campus-Agent"];
    [appMenu addItemWithTitle:@"关于 Campus-Agent" action:@selector(showAbout) keyEquivalent:@""];
    [appMenu addItem:[NSMenuItem separatorItem]];
    [appMenu addItemWithTitle:@"偏好设置..." action:@selector(openSettings) keyEquivalent:@","];
    [appMenu addItem:[NSMenuItem separatorItem]];
    [appMenu addItemWithTitle:@"隐藏 Campus-Agent" action:@selector(hide:) keyEquivalent:@"h"];
    NSMenuItem *hideOthers = [[NSMenuItem alloc] initWithTitle:@"隐藏其他" action:@selector(hideOtherApplications:) keyEquivalent:@"h"];
    [hideOthers setKeyEquivalentModifierMask:(NSEventModifierFlagOption | NSEventModifierFlagCommand)];
    [appMenu addItem:hideOthers];
    [appMenu addItemWithTitle:@"显示全部" action:@selector(unhideAllApplications:) keyEquivalent:@""];
    [appMenu addItem:[NSMenuItem separatorItem]];
    [appMenu addItemWithTitle:@"退出 Campus-Agent" action:@selector(terminate:) keyEquivalent:@"q"];
    appMenuItem.submenu = appMenu;
    [mainMenu addItem:appMenuItem];
    
    // 2. 编辑菜单 (支持 WebView 输入框的复制粘贴)
    NSMenuItem *editMenuItem = [[NSMenuItem alloc] init];
    NSMenu *editMenu = [[NSMenu alloc] initWithTitle:@"编辑"];
    [editMenu addItemWithTitle:@"撤销" action:@selector(undo:) keyEquivalent:@"z"];
    [editMenu addItemWithTitle:@"重做" action:@selector(redo:) keyEquivalent:@"Z"];
    [editMenu addItem:[NSMenuItem separatorItem]];
    [editMenu addItemWithTitle:@"剪切" action:@selector(cut:) keyEquivalent:@"x"];
    [editMenu addItemWithTitle:@"复制" action:@selector(copy:) keyEquivalent:@"c"];
    [editMenu addItemWithTitle:@"粘贴" action:@selector(paste:) keyEquivalent:@"v"];
    [editMenu addItemWithTitle:@"全选" action:@selector(selectAll:) keyEquivalent:@"a"];
    editMenuItem.submenu = editMenu;
    [mainMenu addItem:editMenuItem];
    
    // 3. 视图菜单
    NSMenuItem *viewMenuItem = [[NSMenuItem alloc] init];
    NSMenu *viewMenu = [[NSMenu alloc] initWithTitle:@"视图"];
    [viewMenu addItemWithTitle:@"刷新页面" action:@selector(reloadPage) keyEquivalent:@"r"];
    [viewMenu addItem:[NSMenuItem separatorItem]];
    [viewMenu addItemWithTitle:@"🎛️ Meta Muse 控制看板" action:@selector(loadDashboard) keyEquivalent:@"1"];
    [viewMenu addItemWithTitle:@"🐸 奶蛙动效大剧场" action:@selector(loadNaiWaWidget) keyEquivalent:@"2"];
    [viewMenu addItemWithTitle:@"📑 Swagger API 接口文档" action:@selector(loadDocs) keyEquivalent:@"3"];
    [viewMenu addItem:[NSMenuItem separatorItem]];
    [viewMenu addItemWithTitle:@"切换全屏" action:@selector(toggleFullScreen:) keyEquivalent:@"f"];
    viewMenuItem.submenu = viewMenu;
    [mainMenu addItem:viewMenuItem];
    
    // 4. 控制与指令菜单
    NSMenuItem *controlMenuItem = [[NSMenuItem alloc] init];
    NSMenu *controlMenu = [[NSMenu alloc] initWithTitle:@"控制"];
    [controlMenu addItemWithTitle:@"🔍 立即巡检微信群" action:@selector(triggerInspect) keyEquivalent:@"i"];
    [controlMenu addItemWithTitle:@"🚨 模拟高危 DDL 预警" action:@selector(triggerTestAlert) keyEquivalent:@"A"];
    [controlMenu addItem:[NSMenuItem separatorItem]];
    [controlMenu addItemWithTitle:@"💊 开启/管理状态栏胶囊" action:@selector(toggleMenuBarPill) keyEquivalent:@"m"];
    controlMenuItem.submenu = controlMenu;
    [mainMenu addItem:controlMenuItem];
    
    // 5. 帮助菜单
    NSMenuItem *helpMenuItem = [[NSMenuItem alloc] init];
    NSMenu *helpMenu = [[NSMenu alloc] initWithTitle:@"帮助"];
    [helpMenu addItemWithTitle:@"面向导师汇报白皮书" action:@selector(openPresentationDoc) keyEquivalent:@""];
    [helpMenu addItemWithTitle:@"项目 README 文档" action:@selector(openReadmeDoc) keyEquivalent:@""];
    [helpMenu addItemWithTitle:@"访问 GitHub 仓库" action:@selector(openGitHub) keyEquivalent:@""];
    helpMenuItem.submenu = helpMenu;
    [mainMenu addItem:helpMenuItem];
    
    [NSApp setMainMenu:mainMenu];
}

#pragma mark - 菜单指令实现

- (void)reloadPage {
    [self.webView reload];
}

- (void)loadDashboard {
    NSURL *url = [NSURL URLWithString:[self.serverUrl stringByAppendingString:@"/dashboard"]];
    [self.webView loadRequest:[NSURLRequest requestWithURL:url]];
}

- (void)loadNaiWaWidget {
    NSURL *url = [NSURL URLWithString:[self.serverUrl stringByAppendingString:@"/naiwa"]];
    [self.webView loadRequest:[NSURLRequest requestWithURL:url]];
}

- (void)loadDocs {
    NSURL *url = [NSURL URLWithString:[self.serverUrl stringByAppendingString:@"/docs"]];
    [self.webView loadRequest:[NSURLRequest requestWithURL:url]];
}

- (void)openSettings {
    [self loadDashboard];
}

- (void)showAbout {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Campus-Agent (校园群聊智能降噪与 DDL 预警系统)";
    alert.informativeText = @"版本: 1.0.0 (Native Desktop Client)\n"
                            @"专为高校学生打造的非侵入式环境智能 (Ambient Intelligence) 具身助教系统。\n"
                            @"纯手写 Objective-C Cocoa + WebKit 原生架构，极速、安全、零打扰。\n\n"
                            @"© 2026 Campus-Agent 贡献者与自研探索者。";
    alert.alertStyle = NSAlertStyleInformational;
    [alert runModal];
}

- (void)triggerInspect {
    NSURL *url = [NSURL URLWithString:[self.serverUrl stringByAppendingString:@"/api/v1/rpa/inspect?force=true"]];
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:url];
    req.HTTPMethod = @"POST";
    [[[NSURLSession sharedSession] dataTaskWithRequest:req] resume];
    [self reloadPage];
}

- (void)triggerTestAlert {
    NSURL *url = [NSURL URLWithString:[self.serverUrl stringByAppendingString:@"/api/v1/daemon/test_alert"]];
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:url];
    req.HTTPMethod = @"POST";
    [[[NSURLSession sharedSession] dataTaskWithRequest:req] resume];
}

- (void)toggleMenuBarPill {
    NSURL *url = [NSURL URLWithString:[self.serverUrl stringByAppendingString:@"/api/v1/menubar/start"]];
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:url];
    req.HTTPMethod = @"POST";
    [[[NSURLSession sharedSession] dataTaskWithRequest:req] resume];
}

- (void)openPresentationDoc {
    NSString *docPath = [self.projectRoot stringByAppendingPathComponent:@"PROFESSOR_PRESENTATION.md"];
    [[NSWorkspace sharedWorkspace] openURL:[NSURL fileURLWithPath:docPath]];
}

- (void)openReadmeDoc {
    NSString *docPath = [self.projectRoot stringByAppendingPathComponent:@"README.md"];
    [[NSWorkspace sharedWorkspace] openURL:[NSURL fileURLWithPath:docPath]];
}

- (void)openGitHub {
    [[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:@"https://github.com"]];
}

#pragma mark - 窗口生命周期 (Mac 优雅后台驻留)

- (BOOL)windowShouldClose:(NSWindow *)sender {
    // 点击红叉不强杀进程，优雅隐藏到后台/Dock 栏
    [self.window orderOut:nil];
    return NO;
}

- (BOOL)applicationShouldHandleReopen:(NSApplication *)sender hasVisibleWindows:(BOOL)flag {
    // 点击 Dock 图标时重新显现窗口
    [self.window makeKeyAndOrderFront:nil];
    return YES;
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    NSLog(@"Campus-Agent 桌面客户端正在安全退出...");
}

@end

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        CampusAgentAppDelegate *delegate = [[CampusAgentAppDelegate alloc] init];
        app.delegate = delegate;
        [app run];
    }
    return 0;
}
