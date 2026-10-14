import os
import database
import api
import tkinter as tk
from tkinter import messagebox
import threading
import matplotlib.ticker as mticker
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("TkAgg")  # Tkinter-compatible backend (needed on macOS/Linux)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


# UI colour palette, kept in one dictionary so it is managed in one place
COLORS = {
    "main":    "#132B47",
    "bg_med":  "#13326F",
    "bg_dark": "#0a1929",
    "bg_plot": "#033d7b",
    "accent":  "#086797",
    "accent2": "#4E636F",
    "text":    "#c0d2e0",
    "dim":     "#8f98a0",
    "green":   "#a3cf06",
    "red":     "#d9534f",
    "btn_def": "#2b4a6f",
    "btn_g":   "#4d7a1e",
    "btn_b":   "#1a5275",
    "btn_y":   "#7d6608",
}


class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("🎮 Steam Game Tracker")
        self.geometry("1440x920")
        self.configure(bg=COLORS["main"])
        self.minsize(1080, 720)

        self._search_results = []
        self._watch_list     = []
        self.selected_appid = None
        self.selected_name  = None

        self.v_data_type = tk.StringVar(value="players")   # players | price
        self.v_time_unit = tk.StringVar(value="day")       # hour | day | month
        self.v_status    = tk.StringVar(
            value="  Ready — pick a game on the left or search for one.")
        self.itad_lows   = {}   # historical low prices from ITAD

        database.create_database()
        self.build_main_ui()
        self.refresh_watch_list()

    # ── MAIN LAYOUT ─────────────────────────────────────────────────────────

    def build_main_ui(self):
        header = tk.Frame(self, bg=COLORS["bg_med"], height=58)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="🎮  Steam Game Tracker",
                 font=("Segoe UI", 18, "bold"),
                 bg=COLORS["bg_med"], fg=COLORS["accent2"]).pack(side="left", padx=18, pady=10)

        tk.Label(header,
                 text="  Live player & price tracking  ·  Steam API  ·  SQLite",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg_med"], fg=COLORS["dim"]).pack(side="left", pady=22)

        body = tk.Frame(self, bg=COLORS["main"])
        body.pack(fill="both", expand=True, padx=0, pady=4)

        # The left panel has a fixed width; the right panel takes the rest
        left_frame = tk.Frame(body, bg=COLORS["bg_med"], width=350)
        left_frame.pack(side="left", fill="y", padx=(0, 5))
        left_frame.pack_propagate(False)

        right = tk.Frame(body, bg=COLORS["main"])
        right.pack(side="right", fill="both", expand=True)

        self.build_left_panel(left_frame)
        self.build_right_panel(right)

        # Status bar at the bottom, always shows what is happening
        tk.Label(self, textvariable=self.v_status,
                 bg=COLORS["bg_med"], fg=COLORS["dim"],
                 font=("Segoe UI", 8), anchor="w", padx=10).pack(fill="x", side="bottom")

    # ── LEFT PANEL (scrollable) ─────────────────────────────────────────────

    def build_left_panel(self, parent):
        """Wraps the left panel in a scrollable Canvas."""
        canvas = tk.Canvas(parent, bg=COLORS["bg_med"], highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=COLORS["bg_med"])

        # Update the scroll area whenever the content changes size
        content.bind("<Configure>",
                     lambda *_: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig("content_window", width=e.width))

        canvas.create_window((0, 0), window=content, anchor="nw", tags="content_window")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse-wheel scrolling is active only while the mouse is over the canvas
        canvas.bind("<Enter>",
                    lambda _: canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")))
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.build_left_content(content)

    def build_left_content(self, parent):
        # ── Game search
        s1 = self.section(parent, "🔍 Search  (Steam Store)")
        self.v_search = tk.StringVar()
        search_entry = tk.Entry(s1, textvariable=self.v_search,
                                font=("Segoe UI", 10),
                                bg=COLORS["bg_dark"], fg=COLORS["text"],
                                insertbackground=COLORS["accent2"],
                                relief="flat", bd=5)
        search_entry.pack(fill="x", padx=8, pady=(4, 2))
        search_entry.bind("<Return>", lambda _: self.search())  # Enter starts a search

        self.button(s1, "Search 🔍", self.search).pack(fill="x", padx=8, pady=(0, 4))

        self.lb_search = self.listbox(s1, height=5)
        self.lb_search.pack(fill="x", padx=8, pady=(0, 4))

        self.button(s1, "➕ Add to watch list", self.add_from_search,
                    bg=COLORS["btn_g"]).pack(fill="x", padx=8, pady=(0, 8))

        # ── Watch list
        s2 = self.section(parent, "📋 Watch list")
        self.lb_watch = self.listbox(s2, height=7)
        self.lb_watch.pack(fill="x", padx=8, pady=(4, 4))
        self.lb_watch.bind("<<ListboxSelect>>", self.on_select)

        self.button(s2, "📥  Fetch & save live data",
                    self.fetch_live_data).pack(fill="x", padx=8, pady=2)
        self.button(s2, "📡  Import SteamCharts history", self.import_steamcharts,
                    bg=COLORS["btn_y"]).pack(fill="x", padx=8, pady=2)
        self.button(s2, "💰  ITAD: save TRY price", self.save_itad_price,
                    bg=COLORS["btn_g"]).pack(fill="x", padx=8, pady=(2, 8))

        # ── Chart settings
        s3 = self.section(parent, "📊 Chart settings")

        self.label(s3, "Data type:")
        for value, text in [("players", "👥 Player count"),
                            ("price",   "💰 Price  (₺ TRY)")]:
            tk.Radiobutton(s3, text=text, variable=self.v_data_type, value=value,
                           font=("Segoe UI", 9),
                           bg=COLORS["bg_med"], fg=COLORS["text"],
                           selectcolor=COLORS["bg_dark"],
                           activebackground=COLORS["bg_med"],
                           activeforeground=COLORS["accent2"]).pack(anchor="w", padx=22)

        self.label(s3, "Time unit:", pady=(8, 0))
        for value, text in [("hour",  "⏰ Hourly"),
                            ("day",   "📅 Daily"),
                            ("month", "🗓️ Monthly")]:
            tk.Radiobutton(s3, text=text, variable=self.v_time_unit, value=value,
                           font=("Segoe UI", 9),
                           bg=COLORS["bg_med"], fg=COLORS["text"],
                           selectcolor=COLORS["bg_dark"],
                           activebackground=COLORS["bg_med"],
                           activeforeground=COLORS["accent2"]).pack(anchor="w", padx=22)

        self.label(s3, "Date range:", pady=(8, 0))
        date_frame = tk.Frame(s3, bg=COLORS["bg_med"])
        date_frame.pack(fill="x", padx=10, pady=4)

        for row, label_text, attr, default in [
            (0, "Start:", "e_start",
             (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")),
            (1, "End:",   "e_end",
             datetime.now().strftime("%Y-%m-%d")),
        ]:
            tk.Label(date_frame, text=label_text,
                     bg=COLORS["bg_med"], fg=COLORS["dim"],
                     font=("Segoe UI", 8)).grid(row=row, column=0, sticky="w")
            field = self.entry(date_frame, default, width=11)
            field.grid(row=row, column=1, padx=4, pady=2)
            setattr(self, attr, field)  # sets self.e_start / self.e_end dynamically

        quick_frame = tk.Frame(s3, bg=COLORS["bg_med"])
        quick_frame.pack(fill="x", padx=8, pady=2)
        for label_text, days in [("7 days", 7), ("30 days", 30), ("90 days", 90)]:
            self.button(quick_frame, label_text,
                        lambda d=days: self.quick_range(d),
                        font_size=8).pack(side="left", padx=2)

        self.button(s3, "📈   Draw chart", self.draw_chart,
                    bg=COLORS["btn_b"]).pack(fill="x", padx=8, pady=(6, 10))

    # ── RIGHT PANEL ─────────────────────────────────────────────────────────

    def build_right_panel(self, parent):
        # The Matplotlib figure is embedded in the Tkinter window
        self.figure, self.ax = plt.subplots(figsize=(10, 6))
        self.figure.patch.set_facecolor(COLORS["bg_plot"])
        self.ax.set_facecolor(COLORS["bg_plot"])
        self.ax.set_title(
            "Pick a game on the left and click 'Draw chart'.",
            color=COLORS["dim"], fontsize=10)

        toolbar_frame = tk.Frame(parent, bg=COLORS["main"])
        toolbar_frame.pack(side="bottom", fill="x")

        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)

        # Add Matplotlib's zoom/pan toolbar to the window
        toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        toolbar.update()

    # ── WIDGET HELPERS ──────────────────────────────────────────────────────

    def section(self, parent, title):
        frame = tk.Frame(parent, bg=COLORS["bg_med"])
        frame.pack(fill="x", pady=(8, 0))
        tk.Label(frame, text=title, font=("Segoe UI", 9, "bold"),
                 bg=COLORS["bg_med"], fg=COLORS["accent2"]).pack(
            anchor="w", padx=8, pady=(6, 2))
        tk.Frame(frame, bg=COLORS["accent"], height=1).pack(
            fill="x", padx=8, pady=(0, 2))
        return frame

    def button(self, parent, text, command, bg=None, font_size=9):
        """Frame+Label based button: skips the native macOS look so colours always show."""
        color = bg or COLORS["btn_def"]
        frame = tk.Frame(parent, bg=color, cursor="hand2")
        label = tk.Label(frame, text=text,
                         bg=color, fg="#ffffff",
                         font=("Segoe UI", font_size, "bold"),
                         padx=10, pady=6)
        label.pack(fill="both", expand=True)

        def on_click(*_):
            command()

        # Hover effect: change colour on enter, restore it on leave
        def on_enter(*_):
            frame.config(bg=COLORS["accent"])
            label.config(bg=COLORS["accent"])

        def on_leave(*_):
            frame.config(bg=color)
            label.config(bg=color)

        for w in (frame, label):
            w.bind("<Button-1>", on_click)
            w.bind("<Enter>",    on_enter)
            w.bind("<Leave>",    on_leave)

        return frame

    def listbox(self, parent, height=5):
        return tk.Listbox(parent, height=height,
                          bg=COLORS["main"], fg=COLORS["text"],
                          selectbackground=COLORS["accent"],
                          font=("Segoe UI", 9), relief="flat",
                          activestyle="none", bd=0)

    def label(self, parent, text, pady=(2, 0)):
        tk.Label(parent, text=text, bg=COLORS["bg_med"],
                 fg=COLORS["dim"], font=("Segoe UI", 8, "bold")).pack(
            anchor="w", padx=10, pady=pady)

    def entry(self, parent, default="", width=None):
        kw = {"width": width} if width else {}
        field = tk.Entry(parent, font=("Segoe UI", 9),
                         bg=COLORS["main"], fg=COLORS["text"],
                         insertbackground=COLORS["accent2"],
                         relief="flat", bd=4, **kw)
        field.insert(0, default)
        return field

    # ── ACTIONS ─────────────────────────────────────────────────────────────

    def refresh_watch_list(self):
        self._watch_list = database.DB.all_games()
        self.lb_watch.delete(0, "end")
        for _, name in self._watch_list:
            self.lb_watch.insert("end", name)

    def search(self):
        term = self.v_search.get().strip()
        if not term:
            return
        self.v_status.set("  Searching...")

        def run():
            try:
                results = api.steam_search(term)
                matches = [(r["id"], r["name"]) for r in results]
            except Exception as error:
                self.after(0, lambda: self.v_status.set(f"  Search error: {error}"))
                return

            def update():
                self._search_results = matches
                self.lb_search.delete(0, "end")
                for _, name in matches:
                    self.lb_search.insert("end", name)
                self.v_status.set(f"  {len(matches)} results found.")

            # Tkinter widgets may only be updated from the main thread
            self.after(0, update)

        # The API call runs in the background so the window never freezes
        threading.Thread(target=run, daemon=True).start()

    def add_from_search(self):
        selection = self.lb_search.curselection()
        if not selection:
            messagebox.showwarning("No selection", "Select a game from the list.")
            return
        appid, name = self._search_results[selection[0]]
        database.DB.upsert_game(appid, name)
        self.refresh_watch_list()
        self.v_status.set(f"  '{name}' added to the watch list.")

    def on_select(self, _event):
        selection = self.lb_watch.curselection()
        if not selection:
            return
        self.selected_appid, self.selected_name = self._watch_list[selection[0]]
        self.v_status.set(
            f"  Selected: {self.selected_name}  (AppID: {self.selected_appid})")

    def fetch_live_data(self):
        if not self.selected_appid:
            messagebox.showwarning("No selection", "Select a game from the watch list first.")
            return
        self.v_status.set("  Fetching data...")

        def run():
            try:
                count = api.steam_player_count(self.selected_appid)
                database.DB.save_player_count(self.selected_appid, count)
                details = api.steam_details(self.selected_appid)
                if details:
                    is_free = details.get("is_free", False)
                    database.DB.upsert_game(
                        self.selected_appid, self.selected_name, is_free=is_free)
                    if not is_free and "price_overview" in details:
                        price_info = details["price_overview"]
                        # Steam returns prices in cents, so divide by 100
                        price    = price_info.get("final", 0) / 100
                        original = price_info.get("initial", 0) / 100
                        discount = price_info.get("discount_percent", 0)
                        # Steam Türkiye now lists prices in USD; store them in TRY
                        if price_info.get("currency") == "USD":
                            rate = api.usd_to_try_rate()
                            price, original = price * rate, original * rate
                        database.DB.save_price(
                            self.selected_appid, price, original, discount)
                self.after(0, lambda: self.v_status.set(
                    f"  Live players: {count:,} — saved."))
            except Exception as error:
                self.after(0, lambda: self.v_status.set(
                    f"  Fetch error: {error}"))

        threading.Thread(target=run, daemon=True).start()

    def import_steamcharts(self):
        if not self.selected_appid:
            messagebox.showwarning("No selection", "Select a game from the watch list first.")
            return

        confirmed = messagebox.askyesno(
            "SteamCharts history",
            f"This imports the real monthly player history of\n"
            f"'{self.selected_name}' from SteamCharts.\n"
            "Existing player records will be deleted. Continue?")
        if not confirmed:
            return

        def run():
            try:
                self.after(0, lambda: self.v_status.set(
                    f"  Fetching from SteamCharts: {self.selected_name}..."))

                points = api.steamcharts_history(self.selected_appid)

                if not points:
                    self.after(0, lambda: messagebox.showerror(
                        "No data",
                        f"SteamCharts has no data for {self.selected_name}."))
                    return

                rows = []
                for ts_raw, avg_players in points:
                    if avg_players is None or avg_players <= 0:
                        continue
                    # Milliseconds or seconds? Anything above 1e10 is milliseconds
                    ts_sec = ts_raw / 1000 if ts_raw > 1e10 else ts_raw
                    t = datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S")
                    rows.append((self.selected_appid, int(avg_players), t))

                if not rows:
                    self.after(0, lambda: messagebox.showerror(
                        "No data", "No valid player data found."))
                    return

                # Delete the old records, then insert the history in one batch
                with database.DB.connect() as conn:
                    conn.execute(
                        "DELETE FROM player_counts WHERE appid=?", (self.selected_appid,))
                    conn.executemany(
                        "INSERT INTO player_counts(appid, player_count, timestamp)"
                        " VALUES (?,?,?)",
                        rows)

                ts0 = points[0][0]
                first_date = datetime.fromtimestamp(
                    ts0 / 1000 if ts0 > 1e10 else ts0).strftime("%Y-%m-%d")
                today = datetime.now().strftime("%Y-%m-%d")

                def update_range():
                    self.e_start.delete(0, "end")
                    self.e_start.insert(0, first_date)
                    self.e_end.delete(0, "end")
                    self.e_end.insert(0, today)
                    self.v_time_unit.set("month")
                    self.v_status.set(
                        f"  Imported {len(rows)} monthly data points:"
                        f" {self.selected_name}  —  switched to the monthly view.")

                self.after(0, update_range)

            except Exception as error:
                self.after(0, lambda: messagebox.showerror(
                    "Connection error",
                    f"Could not reach SteamCharts:\n{error}\n\n"
                    "Check your internet connection."))
                self.after(0, lambda: self.v_status.set(
                    "  SteamCharts connection error."))

        threading.Thread(target=run, daemon=True).start()

    def save_itad_price(self):
        if not self.selected_appid:
            messagebox.showwarning("No selection", "Select a game from the watch list first.")
            return
        if database.DB.is_free_game(self.selected_appid):
            messagebox.showinfo("Free game",
                f"'{self.selected_name}' is free to play, so it has no price data.")
            return

        # The API key comes from the environment, never from the code
        api_key = os.environ.get("ITAD_API_KEY")
        if not api_key:
            messagebox.showwarning(
                "Missing API key",
                "Set the ITAD_API_KEY environment variable to use price features.\n\n"
                "export ITAD_API_KEY=your_key_here")
            return

        def run():
            try:
                self.after(0, lambda: self.v_status.set(
                    f"  Fetching TRY price from ITAD: {self.selected_name}..."))

                info = api.itad_price_info(api_key, self.selected_appid)

                if not info or info["current"] is None:
                    self.after(0, lambda: messagebox.showwarning(
                        "No data",
                        f"ITAD has no Steam Türkiye price\n"
                        f"for '{self.selected_name}'."))
                    self.after(0, lambda: self.v_status.set("  No price found on ITAD."))
                    return

                database.DB.save_price(
                    self.selected_appid,
                    info["current"], info["regular"], info["discount"])

                # Keep the historical lows in memory for the chart's reference lines
                self.itad_lows = info["lows"]

                lows = info["lows"]
                def update():
                    self.v_data_type.set("price")
                    self.v_status.set(
                        f"  {self.selected_name} — Now: ₺{info['current']:,.0f}"
                        f"  |  3-month low: ₺{lows['three_months']:,.0f}"
                        f"  |  1-year low: ₺{lows['one_year']:,.0f}"
                        f"  |  All-time low: ₺{lows['all_time']:,.0f}")

                self.after(0, update)

            except Exception as error:
                self.after(0, lambda: messagebox.showerror(
                    "ITAD error", f"Could not reach ITAD:\n{error}"))
                self.after(0, lambda: self.v_status.set("  ITAD connection error."))

        threading.Thread(target=run, daemon=True).start()

    def quick_range(self, days):
        end   = datetime.now()
        start = end - timedelta(days=days)
        self.e_start.delete(0, "end")
        self.e_start.insert(0, start.strftime("%Y-%m-%d"))
        self.e_end.delete(0, "end")
        self.e_end.insert(0, end.strftime("%Y-%m-%d"))

    def draw_chart(self):
        if not self.selected_appid:
            messagebox.showwarning("No selection", "Select a game from the watch list first.")
            return
        start     = self.e_start.get().strip()
        end       = self.e_end.get().strip()
        data_type = self.v_data_type.get()
        time_unit = self.v_time_unit.get()

        # Validate the dates the user typed
        try:
            datetime.strptime(start, "%Y-%m-%d")
            datetime.strptime(end,   "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid date", "Use the YYYY-MM-DD format.")
            return

        if data_type == "price" and database.DB.is_free_game(self.selected_appid):
            messagebox.showinfo(
                "Free game",
                f"'{self.selected_name}' is free to play,\n"
                "so it has no price data.")
            return

        self.v_status.set("  Drawing chart...")

        def run():
            if data_type == "players":
                rows = database.DB.player_history(
                    self.selected_appid, start, end + " 23:59:59", time_unit)
            else:
                rows = database.DB.price_history(
                    self.selected_appid, start, end + " 23:59:59")

            if not rows:
                self.after(0, lambda: messagebox.showinfo(
                    "No data",
                    "No data in this date range.\nFetch some data first."))
                self.after(0, lambda: self.v_status.set("  No data found."))
                return

            self.after(0, lambda: self._plot(rows, data_type, time_unit))

        threading.Thread(target=run, daemon=True).start()

    def _plot(self, rows, data_type, time_unit):
        self.ax.clear()
        self.ax.set_facecolor(COLORS["bg_plot"])

        # Pick the date format that matches the time unit
        formats = {
            "hour":  "%Y-%m-%d %H:%M:%S",
            "day":   "%Y-%m-%d",
            "month": "%Y-%m",
        }
        fmt = formats.get(
            time_unit if data_type == "players" else "day", "%Y-%m-%d")

        try:
            dates = [datetime.strptime(r[0], fmt) for r in rows]
        except ValueError:
            # If the format does not match, keep only the day part
            dates = [datetime.strptime(r[0][:10], "%Y-%m-%d") for r in rows]

        values = [r[1] for r in rows]

        color = COLORS["green"] if data_type == "players" else COLORS["accent2"]
        label = "Player count" if data_type == "players" else "Price (₺)"

        self.ax.plot(dates, values, color=color, linewidth=2.0,
                     label=label, zorder=3)
        self.ax.fill_between(dates, values, alpha=0.12, color=color, zorder=2)

        # ── Y axis: shorten big numbers with K/M, show prices with ₺
        if data_type == "players":
            self.ax.yaxis.set_major_formatter(mticker.FuncFormatter(
                lambda x, _: (f"{x/1_000_000:.1f}M" if x >= 1_000_000
                              else f"{x/1000:.0f}K" if x >= 1000
                              else f"{x:.0f}")))
        else:
            self.ax.yaxis.set_major_formatter(mticker.FuncFormatter(
                lambda x, _: f"₺{x:,.0f}"))

        # ── Label the highest and lowest points on the chart
        if len(values) > 1 and max(values) != min(values):
            def _format(v):
                if data_type == "players":
                    return (f"{v/1_000_000:.2f}M" if v >= 1_000_000
                            else f"{v/1000:.1f}K" if v >= 1000
                            else f"{v:.0f}")
                return f"₺{v:,.0f}"

            max_i = values.index(max(values))
            min_i = values.index(min(values))

            for i, point_color, offset in [
                (max_i, COLORS["green"], 10),
                (min_i, COLORS["red"],  -16),
            ]:
                self.ax.annotate(
                    _format(values[i]),
                    xy=(dates[i], values[i]),
                    xytext=(0, offset), textcoords="offset points",
                    color=point_color, fontsize=8, ha="center",
                    fontweight="bold", clip_on=False)

        self.ax.set_title(f"{self.selected_name} — {label}",
                          color=COLORS["text"], fontsize=12, pad=12)
        self.ax.set_xlabel("Date", color=COLORS["dim"], labelpad=8)
        self.ax.set_ylabel(label, color=COLORS["dim"], labelpad=8)
        self.ax.tick_params(colors=COLORS["dim"], which="both")

        if time_unit == "month" and data_type == "players":
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        else:
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

        for spine in self.ax.spines.values():
            spine.set_edgecolor(COLORS["accent"])
            spine.set_alpha(0.4)

        # Draw ITAD's historical lows as horizontal reference lines
        if data_type == "price" and self.itad_lows:
            refs = [
                (self.itad_lows.get("three_months"), "3-month low", COLORS["accent2"]),
                (self.itad_lows.get("one_year"),     "1-year low",  COLORS["dim"]),
                (self.itad_lows.get("all_time"),     "All-time low", COLORS["red"]),
            ]
            for value, name, ref_color in refs:
                if value:
                    self.ax.axhline(value, color=ref_color, linewidth=1,
                                    linestyle=":", alpha=0.8,
                                    label=f"{name} ₺{value:,.0f}")

        self.figure.autofmt_xdate(rotation=30)
        self.ax.legend(facecolor=COLORS["main"], edgecolor=COLORS["accent"],
                       labelcolor=COLORS["text"])
        self.ax.grid(True, color=COLORS["accent"], alpha=0.15,
                     linestyle="--", zorder=1)
        self.figure.tight_layout()
        self.canvas.draw()
        self.v_status.set(
            f"  {self.selected_name} — {len(rows)} data points drawn.")


if __name__ == "__main__":
    App().mainloop()
