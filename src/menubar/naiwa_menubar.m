//
//  naiwa_menubar.m
//  Campus-Agent macOS Native Menu Bar Pill (NSStatusBar Companion)
//
//  Created for Campus-Agent 奶蛙 (NaiWa)
//

#import <Cocoa/Cocoa.h>

@interface NaiwaMenuBarApp : NSObject <NSApplicationDelegate>

@property (strong, nonatomic) NSStatusItem *statusItem;
@property (strong, nonatomic) NSMenu *menu;
@property (strong, nonatomic) NSTimer *pollTimer;

// Dynamic Menu Items
@property (strong, nonatomic) NSMenuItem *headerItem;
@property (strong, nonatomic) NSMenuItem *statusItemRow;
@property (strong, nonatomic) NSMenuItem *idleItemRow;
@property (strong, nonatomic) NSMenuItem *urgentItemRow;
@property (strong, nonatomic) NSMenuItem *toggleDaemonItem;

@property (assign, nonatomic) BOOL isDaemonEnabled;
@property (strong, nonatomic) NSString *serverBaseUrl;

@end

@implementation NaiwaMenuBarApp

- (instancetype)init {
    self = [super init];
    if (self) {
        _isDaemonEnabled = YES;
        _serverBaseUrl = @"http://127.0.0.1:8000";
    }
    return self;
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    // 1. 设置为 Accessory 模式：只驻留菜单栏，不占用 Dock，不显现主窗口
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];

    // 2. 挂载 NSStatusBar 状态项 (紧凑宽度，防 MacBook 刘海屏遮挡)
    NSStatusBar *statusBar = [NSStatusBar systemStatusBar];
    self.statusItem = [statusBar statusItemWithLength:NSVariableStatusItemLength];
    
    if (self.statusItem.button) {
        // 使用紧凑型原生 Emoji 与简明标题，确保即使菜单栏图标较多也能稳固显现
        self.statusItem.button.title = @"🐸 奶蛙";
        self.statusItem.button.toolTip = @"奶蛙 (NaiWa) 校园智能学伴 - 点击展开快捷微面板";
    }

    // 3. 构建富交互下拉菜单
    [self setupMenu];
    self.statusItem.menu = self.menu;

    // 4. 立即触发一次状态同步，并启动 3 秒轻量轮询
    [self fetchDaemonStatus];
    self.pollTimer = [NSTimer scheduledTimerWithTimeInterval:3.0
                                                     target:self
                                                   selector:@selector(fetchDaemonStatus)
                                                   userInfo:nil
                                                    repeats:YES];
    [[NSRunLoop currentRunLoop] addTimer:self.pollTimer forMode:NSRunLoopCommonModes];
}

- (void)setupMenu {
    self.menu = [[NSMenu alloc] initWithTitle:@"NaiwaMenu"];

    // 头部信息
    self.headerItem = [[NSMenuItem alloc] initWithTitle:@"🐸 奶蛙 (NaiWa) 校园守护胶囊" action:nil keyEquivalent:@""];
    [self.headerItem setEnabled:NO];
    [self.menu addItem:self.headerItem];

    // 运行状态与空闲避让
    self.statusItemRow = [[NSMenuItem alloc] initWithTitle:@"  ● 运行态势: 正在连接核心服务..." action:nil keyEquivalent:@""];
    [self.statusItemRow setEnabled:NO];
    [self.menu addItem:self.statusItemRow];

    self.idleItemRow = [[NSMenuItem alloc] initWithTitle:@"  ● 外设感知: 监听物理键鼠中..." action:nil keyEquivalent:@""];
    [self.idleItemRow setEnabled:NO];
    [self.menu addItem:self.idleItemRow];

    // 高危待办通知
    self.urgentItemRow = [[NSMenuItem alloc] initWithTitle:@"  ● 最近待办: 暂无临界高危 DDL" action:nil keyEquivalent:@""];
    [self.urgentItemRow setEnabled:NO];
    [self.menu addItem:self.urgentItemRow];

    [self.menu addItem:[NSMenuItem separatorItem]];

    // 核心操作
    NSMenuItem *triggerItem = [[NSMenuItem alloc] initWithTitle:@"⚡ 立即执行一次微信群巡检" action:@selector(triggerPatrol:) keyEquivalent:@"r"];
    [triggerItem setTarget:self];
    [self.menu addItem:triggerItem];

    self.toggleDaemonItem = [[NSMenuItem alloc] initWithTitle:@"🤖 守护巡检: 运行中 (点击切换)" action:@selector(toggleDaemon:) keyEquivalent:@"t"];
    [self.toggleDaemonItem setTarget:self];
    [self.menu addItem:self.toggleDaemonItem];

    NSMenuItem *testAlertItem = [[NSMenuItem alloc] initWithTitle:@"🚨 模拟高危 DDL 声光预警" action:@selector(testAlert:) keyEquivalent:@"a"];
    [testAlertItem setTarget:self];
    [self.menu addItem:testAlertItem];

    [self.menu addItem:[NSMenuItem separatorItem]];

    // 网页与大剧场直达
    NSMenuItem *dashboardItem = [[NSMenuItem alloc] initWithTitle:@"🖥️ 打开控制台 (Meta Muse)" action:@selector(openDashboard:) keyEquivalent:@"d"];
    [dashboardItem setTarget:self];
    [self.menu addItem:dashboardItem];

    NSMenuItem *naiwaItem = [[NSMenuItem alloc] initWithTitle:@"🐾 打开奶蛙活体桌宠大剧场" action:@selector(openNaiwaWidget:) keyEquivalent:@"w"];
    [naiwaItem setTarget:self];
    [self.menu addItem:naiwaItem];

    [self.menu addItem:[NSMenuItem separatorItem]];

    // 退出
    NSMenuItem *quitItem = [[NSMenuItem alloc] initWithTitle:@"❌ 退出状态栏常驻" action:@selector(quitApp:) keyEquivalent:@"q"];
    [quitItem setTarget:self];
    [self.menu addItem:quitItem];
}

#pragma mark - HTTP Remote Telemetry

- (void)fetchDaemonStatus {
    NSURL *url = [NSURL URLWithString:[NSString stringWithFormat:@"%@/api/v1/daemon/status", self.serverBaseUrl]];
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
    [request setTimeoutInterval:2.5];

    NSURLSessionDataTask *task = [[NSURLSession sharedSession] dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        if (error || !data) {
            dispatch_async(dispatch_get_main_queue(), ^{
                self.statusItem.button.title = @"🐸 奶蛙";
                self.statusItemRow.title = @"  ● 运行态势: 后端服务未连接 (端口 8000)";
            });
            return;
        }

        NSError *jsonError = nil;
        NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:&jsonError];
        if (!json || jsonError) {
            return;
        }

        dispatch_async(dispatch_get_main_queue(), ^{
            [self updateUIWithStatusJson:json];
        });
    }];
    [task resume];
}

- (void)updateUIWithStatusJson:(NSDictionary *)json {
    BOOL enabled = [json[@"enabled"] boolValue];
    NSString *status = json[@"status"] ?: @"idle";
    double idleSecs = [json[@"idle_seconds"] doubleValue];
    double idleThreshold = [json[@"idle_threshold"] doubleValue] ?: 45.0;
    NSArray *alerts = json[@"urgent_alerts_history"] ?: @[];

    self.isDaemonEnabled = enabled;

    // 1. 更新菜单项文本
    if (!enabled) {
        self.toggleDaemonItem.title = @"🤖 守护巡检: 已暂停 (点击启用)";
        self.statusItemRow.title = @"  ● 运行态势: 暂停中";
        self.idleItemRow.title = [NSString stringWithFormat:@"  ● 物理空闲: %.1fs (已暂停避让)", idleSecs];
        self.statusItem.button.title = @"🐸 暂停";
    } else {
        self.toggleDaemonItem.title = @"🤖 守护巡检: 守护中 (点击暂停)";
        if ([status isEqualToString:@"inspecting"]) {
            self.statusItemRow.title = @"  ● 运行态势: 正在静默巡检微信群...";
            self.statusItem.button.title = @"🐸 巡检中";
        } else if ([status isEqualToString:@"yielding"]) {
            self.statusItemRow.title = @"  ● 运行态势: 避让中 (用户正使用键盘/鼠标)";
            self.statusItem.button.title = @"🐸 避让中";
        } else {
            self.statusItemRow.title = @"  ● 运行态势: 静默待命中 (全周期守护)";
            self.statusItem.button.title = @"🐸 奶蛙";
        }
        
        if (idleSecs < idleThreshold) {
            self.idleItemRow.title = [NSString stringWithFormat:@"  ● 物理空闲: %.1fs (低于 %.0fs 避让线)", idleSecs, idleThreshold];
        } else {
            self.idleItemRow.title = [NSString stringWithFormat:@"  ● 物理空闲: %.1fs (就绪静默执行)", idleSecs];
        }
    }

    // 2. 检查是否有高危 DDL
    if (alerts.count > 0) {
        NSDictionary *latestAlert = alerts.firstObject;
        NSString *urgentTitle = latestAlert[@"task_title"] ?: @"临界待办";
        double hoursLeft = [latestAlert[@"hours_left"] doubleValue];
        
        if (hoursLeft <= 24.0) {
            self.urgentItemRow.title = [NSString stringWithFormat:@"  🚨 高危待办: %@ (剩 %.1fh)", urgentTitle, hoursLeft];
            if (hoursLeft <= 12.0) {
                self.statusItem.button.title = [NSString stringWithFormat:@"🚨 %.1fh", hoursLeft];
            }
        } else {
            self.urgentItemRow.title = [NSString stringWithFormat:@"  ● 最近待办: %@ (%.1fh)", urgentTitle, hoursLeft];
        }
    } else {
        self.urgentItemRow.title = @"  ● 最近待办: 暂无临界高危 DDL";
    }
}

#pragma mark - Actions

- (void)triggerPatrol:(id)sender {
    [self sendPostRequest:@"/api/v1/daemon/trigger"];
    self.statusItem.button.title = @"🐸 巡检中";
}

- (void)toggleDaemon:(id)sender {
    [self sendPostRequest:@"/api/v1/daemon/toggle"];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        [self fetchDaemonStatus];
    });
}

- (void)testAlert:(id)sender {
    [self sendPostRequest:@"/api/v1/daemon/test_alert"];
}

- (void)openDashboard:(id)sender {
    NSURL *url = [NSURL URLWithString:[NSString stringWithFormat:@"%@/dashboard", self.serverBaseUrl]];
    [[NSWorkspace sharedWorkspace] openURL:url];
}

- (void)openNaiwaWidget:(id)sender {
    NSURL *url = [NSURL URLWithString:[NSString stringWithFormat:@"%@/naiwa", self.serverBaseUrl]];
    [[NSWorkspace sharedWorkspace] openURL:url];
}

- (void)quitApp:(id)sender {
    [NSApp terminate:nil];
}

- (void)sendPostRequest:(NSString *)endpoint {
    NSURL *url = [NSURL URLWithString:[NSString stringWithFormat:@"%@%@", self.serverBaseUrl, endpoint]];
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
    [request setHTTPMethod:@"POST"];
    [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];

    NSURLSessionDataTask *task = [[NSURLSession sharedSession] dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        if (error) {
            NSLog(@"[NaiwaMenuBar] Request failed: %@", error.localizedDescription);
        } else {
            NSLog(@"[NaiwaMenuBar] Request to %@ succeeded", endpoint);
        }
    }];
    [task resume];
}

@end

int main(int argc, const char * argv[]) {
    if (argc > 1 && strcmp(argv[1], "--test-compile") == 0) {
        printf("NaiWa MenuBar Binary OK\n");
        return 0;
    }

    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        [app setActivationPolicy:NSApplicationActivationPolicyAccessory];
        NaiwaMenuBarApp *delegate = [[NaiwaMenuBarApp alloc] init];
        [app setDelegate:delegate];
        [app finishLaunching];
        [app run];
    }
    return 0;
}
