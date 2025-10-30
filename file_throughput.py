# -*- coding: utf-8 -*-
import os
import subprocess
import configparser
import time
import hashlib
import sys
import argparse
import matplotlib.pyplot as plt
import matplotlib
from fpdf import FPDF


def generate_files(sizes, count_per_size=10):
    """
    生成指定大小和数量的数据文件。
    """
    for size_name, size_flag in sizes:
        for i in range(1, count_per_size + 1):
            filename = f'{size_name}_{i}.dat'
            cmd = [
                'dd', 'if=/dev/zero',
                f'of={filename}',
                'bs=1',
                'count=0',
                f'seek={size_flag}'
            ]
            print(f"正在生成文件: {filename}")
            subprocess.run(' '.join(cmd), shell=True, check=True)

def get_config(config_path='config.ini'):
    """
    读取配置文件，返回传输ip、ssh登录ip、端口、账号、密码、密钥路径、远端目录。
    远端登录的ip和端口都和传输用的不一样。
    """
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    # 传输用的ip和端口
    target_ip = config.get('DEFAULT', 'target_ip')
    target_port = config.get('DEFAULT', 'port')
    # ssh登录用的ip和端口
    ssh_ip = config.get('DEFAULT', 'ssh_ip', fallback=target_ip)
    ssh_port = config.get('DEFAULT', 'ssh_port', fallback=target_port)
    username = config.get('DEFAULT', 'username')
    password = config.get('DEFAULT', 'password')
    key_path = config.get('DEFAULT', 'key_path')
    remote_dir = config.get('DEFAULT', 'remote_dir', fallback='/file_transport')
    return target_ip, target_port, ssh_ip, ssh_port, username, password, key_path, remote_dir

def collect_file_list(sizes, count_per_size=10):
    """
    收集所有生成的文件名。
    """
    file_list = []
    for size_name, _ in sizes:
        for i in range(1, count_per_size + 1):
            filename = f'{size_name}_{i}.dat'
            file_list.append(filename)
    return file_list

def build_rayfilec_cmd(target_ip, port, username, password, file_list, remote_dir):
    """
    构造rayfile-c命令。
    """
    base_cmd = [
        'rayfile-c',
        '-a', target_ip,
        '-P', port,
        '-u', username,
        '-w', password,
        '-tm',
        '-no-meta',
        '-symbolic-links', 'follow',
        '-retry', '10',
        '-retrytimeout', '30',
        '-o', 'upload',
        '-d', remote_dir,
    ]
    for filename in file_list:
        base_cmd.extend(['-s', filename])
    return base_cmd

def calc_total_size(file_list):
    """
    计算所有文件的总大小（字节）。
    """
    total_size = 0
    for filename in file_list:
        if os.path.exists(filename):
            total_size += os.path.getsize(filename)
    return total_size

def calc_local_md5(filename):
    """
    计算本地文件的md5值。
    """
    hash_md5 = hashlib.md5()
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_remote_md5(ssh_ip, ssh_port, username, key_path, remote_dir, filename):
    """
    通过ssh密钥登录远端，获取远端文件的md5值。
    注意：ssh_ip和ssh_port用于远端登录。
    这里需要获取远端的绝对路径，否则~会被本地shell解释，导致路径错误。
    """
    # 先通过ssh获取远端家目录
    get_home_cmd = [
        'ssh',
        '-i', key_path,
        '-p', str(ssh_port),
        '-o', 'StrictHostKeyChecking=no',
        f'{username}@{ssh_ip}',
        'pwd'
    ]
    try:
        home_result = subprocess.run(get_home_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', timeout=100)
        remote_home = home_result.stdout.strip()
        if not remote_home:
            print("无法获取远端家目录，md5校验失败。")
            return None
    except Exception as e:
        print(f"获取远端家目录失败: {e}")
        return None

    # 拼接远端绝对路径
    if remote_dir.startswith("/"):
        remote_dir = remote_dir[1:]
    remote_path = os.path.join(remote_home, remote_dir, filename)

    # 兼容不同系统的md5sum命令
    md5_cmd = f"if command -v md5sum >/dev/null 2>&1; then md5sum '{remote_path}'; elif command -v md5 >/dev/null 2>&1; then md5 '{remote_path}'; else echo 'no_md5_tool'; fi"
    ssh_cmd = [
        'ssh',
        '-i', key_path,
        '-p', str(ssh_port),
        '-o', 'StrictHostKeyChecking=no',
        f'{username}@{ssh_ip}',
        md5_cmd
    ]
    try:
        result = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', timeout=60)
        output = result.stdout.strip()
        if 'no_md5_tool' in output or result.returncode != 0:
            print(f"远端未找到md5工具或命令执行失败: {output}")
            return None
        # 解析md5值
        if 'md5sum' in md5_cmd:
            # 形如: md5hash  filename
            md5_value = output.split()[0]
        elif 'md5 ' in output:
            # macOS: MD5 (filename) = md5hash
            md5_value = output.split('=')[-1].strip()
        else:
            md5_value = output.split()[0]
        return md5_value
    except Exception as e:
        print(f"获取远端md5失败: {e}")
        return None

def check_files_integrity(file_list, ssh_ip, ssh_port, username, key_path, remote_dir):
    """
    检查本地和远端文件的md5值是否一致。
    返回：列表 [ (filename, 本地md5, 远端md5, 是否一致) , ... ]
    """
    result_details = []
    all_pass = True
    for filename in file_list:
        print(f"正在校验文件: {filename}")
        local_md5 = calc_local_md5(filename)
        remote_md5 = get_remote_md5(ssh_ip, ssh_port, username, key_path, remote_dir, filename)
        identical = (remote_md5 is not None and local_md5 == remote_md5)
        result_details.append( (filename, local_md5, remote_md5, identical) )
        if not identical:
            if remote_md5 is None:
                print(f"文件 {filename} 远端md5获取失败，跳过校验。")
            else:
                print(f"文件 {filename} 校验失败！本地md5: {local_md5}, 远端md5: {remote_md5}")
            all_pass = False
        else:
            print(f"文件 {filename} 校验通过。")
    return all_pass, result_details

def plot_speed_chart(size_list, speed_list, output_png):
    plt.figure(figsize=(8,6))
    plt.bar(size_list, speed_list, color=['#5B9BD5','#ED7D31','#A5A5A5','#FFC000'])
    plt.xlabel('File Type')
    plt.ylabel('Average Transfer Speed (MB/s)')
    plt.title('Average Transfer Speed for Different File Types')
    for i, v in enumerate(speed_list):
        plt.text(i, v, f"{v:.2f}", ha='center', va='bottom', fontsize=10)
    plt.tight_layout()
    plt.savefig(output_png)
    plt.close()

class PDFReport(FPDF):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_auto_page_break(auto=True, margin=15)
        # Removed SimHei or Chinese font setup

    def header(self):
        pass

    def set_title_utf8(self, title):
        try:
            self.set_title(title)
        except Exception:
            self.set_title("Report")

    def add_section_title(self, text, h=10):
        self.set_font("Arial", size=16)
        self.cell(0, h, text, new_x="LMARGIN", new_y="NEXT", align='L')

    def add_subtitle(self, text, h=8):
        self.set_font("Arial", size=13)
        self.cell(0, h, text, ln=1, align='L')

    def add_par(self, text, h=7):
        self.set_font("Arial", size=11)
        self.multi_cell(0, h, text)

    def add_kv_table(self, kvlist, col_widths, header_row=None):
        self.set_font("Arial", '', 11)
        line_height = 7
        # Draw header if provided
        if header_row:
            self.set_fill_color(220, 220, 220)
            self._draw_table_row(header_row, col_widths, line_height=line_height, fill=True, align_list=['C']*len(header_row))
        # Draw data rows
        self.set_fill_color(255, 255, 255)
        for row in kvlist:
            self._draw_table_row([str(v) for v in row], col_widths, line_height=line_height)

    def _split_text_to_fit_width(self, text, max_width):
        # Split text into multiple lines so each line width <= max_width
        if text is None:
            return [""]
        text = str(text)
        words = text.split(' ')
        lines = []
        current = ""
        for word in words:
            # If word itself is too long (no spaces), split by characters
            if self.get_string_width(word) > max_width:
                # First flush current
                if current:
                    lines.append(current)
                    current = ""
                chunk = ""
                for ch in word:
                    if self.get_string_width(chunk + ch) <= max_width:
                        chunk += ch
                    else:
                        lines.append(chunk)
                        chunk = ch
                if chunk:
                    lines.append(chunk)
            else:
                candidate = word if not current else current + ' ' + word
                if self.get_string_width(candidate) <= max_width:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    current = word
        if current:
            lines.append(current)
        # Ensure at least one line
        if not lines:
            lines = [""]
        return lines

    def _draw_table_row(self, values, col_widths, line_height=7, border=1, fill=False, align_list=None):
        # 预览如果当前行加上高度后是否会溢出页面，如果会，强制换页并画表头
        x_start = self.get_x()
        y_start = self.get_y()
        lines_per_cell = []
        for i, value in enumerate(values):
            w = col_widths[i] if i < len(col_widths) else 40
            lines = self._split_text_to_fit_width(value, w - 2)  # small padding
            lines_per_cell.append(lines)
        max_lines = max(len(lines) for lines in lines_per_cell)
        row_height = line_height * max_lines
        PAGE_HEIGHT = self.h - self.b_margin

        # 自定义表格分页机制
        # 若当前Y+row_height超出底部，且不是在页面顶部，换页并重绘表头
        if (y_start + row_height > PAGE_HEIGHT) and (y_start > self.t_margin + 5):
            self.add_page()
            # 如果有全局变量或实例属性 self._last_table_header_row, self._last_table_col_widths，可以在这里重绘header
            if hasattr(self, '_cur_table_header_row') and hasattr(self, '_cur_table_col_widths') and self._cur_table_header_row is not None:
                # 递归调用画header
                self.set_fill_color(220, 220, 220)
                self._draw_table_row(self._cur_table_header_row, self._cur_table_col_widths, line_height=line_height, fill=True, align_list=['C']*len(self._cur_table_header_row))
            # 新页面新起点
            x_start = self.get_x()
            y_start = self.get_y()
        # Draw border + cell content
        for i, lines in enumerate(lines_per_cell):
            w = col_widths[i] if i < len(col_widths) else 40
            x = self.get_x()
            y = self.get_y()
            self.rect(x, y, w, row_height)
            self.set_xy(x + 1, y)  # left padding 1mm
            align = 'L'
            if align_list and i < len(align_list):
                align = align_list[i]
            for line in lines:
                self.cell(w - 2, line_height, line, ln=1, border=0, align=align)
            self.set_xy(x + w, y)
        self.set_xy(x_start, y_start + row_height)

    def add_table_with_auto_header(self, data_rows, col_widths, header_row, line_height=7, align_list=None):
        # 将当前表头和列宽传给实例属性，供自动分页时使用
        self._cur_table_header_row = header_row
        self._cur_table_col_widths = col_widths
        # header
        self.set_fill_color(220,220,220)
        self._draw_table_row(header_row, col_widths, line_height=line_height, fill=True, align_list=align_list)
        # rows
        self.set_fill_color(255,255,255)
        for row in data_rows:
            self._draw_table_row([str(v) for v in row], col_widths, line_height=line_height, align_list=align_list)
        # 恢复context，防止下表污染
        self._cur_table_header_row = None
        self._cur_table_col_widths = None

    def add_image_centered(self, img_path, width=120):
        if os.path.exists(img_path):
            self.ln(2)
            x = (210 - width)/2  # Center the image
            self.image(img_path, x=x, w=width)
            self.ln(5)
        else:
            self.add_par("(Image not found)")

def generate_pdf_report(pdf_filename, items, speed_chart_png, config_info, overall_stats, integrity_results):
    pdf = PDFReport(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_title_utf8('Data Transfer Performance Evaluation Report')

    # Title
    pdf.set_font("Arial", size=20)
    pdf.cell(0, 15, 'Data Transfer Performance Evaluation Report', align='C', ln=1)
    pdf.ln(3)

    # 1. Configuration Information
    pdf.add_section_title('1. Test Configuration Information')
    configs = [[key, str(val)] for key, val in config_info.items()]
    pdf.add_kv_table(configs, [40, 120], header_row=None)
    pdf.ln(5)

    # 2. Overall Statistics
    pdf.add_section_title('2. Overall Statistics')
    overall_table = [[key, str(val)] for key, val in overall_stats.items()]
    pdf.add_kv_table(overall_table, [60, 60], header_row=None)
    pdf.ln(5)

    # 3. Transfer Speed Chart
    pdf.add_section_title('3. Average Transfer Speed by File Type')
    pdf.add_image_centered(speed_chart_png, width=120)
    pdf.ln(3)

    # 4. Data Integrity Check Results
    pdf.add_section_title('4. Data Integrity Check Results')
    check_result_header = ["Filename", "Local md5", "Remote md5", "Consistency"]
    check_result_rows = []
    for filename, local_md5, remote_md5, identical in integrity_results:
        if remote_md5 is None:
            status = "Failed to get remote md5"
            local_md5_short = local_md5[:15] if local_md5 else "-"
            remote_md5_short = "-"
        else:
            status = "Pass" if identical else "Fail"
            local_md5_short = local_md5[:15] if local_md5 else "-"
            remote_md5_short = remote_md5[:15] if remote_md5 else "-"
        check_result_rows.append([filename, local_md5_short, remote_md5_short, status])
    col_widths = [50, 45, 45, 25]
    line_height = 7
    pdf.set_font("Arial", size=11)
    # 注意: 新表格绘制方式，支持自动分页和表头复用
    # 支持高亮状态
    data_rows = []
    # 先绘制表头，逐条绘制数据（支持高亮color）
    pdf._cur_table_header_row = check_result_header
    pdf._cur_table_col_widths = col_widths
    # header
    pdf.set_fill_color(220, 220, 220)
    pdf._draw_table_row(check_result_header, col_widths, line_height=line_height, fill=True, align_list=['C']*len(check_result_header))
    # data
    for row in check_result_rows:
        # 高亮颜色
        if row[3] == 'Fail':
            pdf.set_text_color(255, 0, 0)
        elif row[3] == 'Failed to get remote md5':
            pdf.set_text_color(255, 140, 0)
        elif row[3] == 'Pass':
            pdf.set_text_color(0, 160, 60)
        else:
            pdf.set_text_color(0, 0, 0)
        pdf._draw_table_row([str(c) for c in row], col_widths, line_height=line_height)
        pdf.set_text_color(0, 0, 0)
    pdf._cur_table_header_row = None
    pdf._cur_table_col_widths = None
    pdf.output(pdf_filename)

def file_throughput(config_path='config.ini'):
    sizes = [
        ('10GB', '10G'),
        ('1GB', '1G'),
        ('100MB', '100M'),
        ('1KB', '1K')
    ]
    # 生成文件
    generate_files(sizes)
    # 读取配置
    target_ip, target_port, ssh_ip, ssh_port, username, password, key_path, remote_dir = get_config(config_path)
    config_info = {
        "Target IP": target_ip,
        "Target Port": target_port,
        "SSH Login IP": ssh_ip,
        "SSH Port": ssh_port,
        "Username": username,
        "Key Path": key_path,
        "Remote Directory": remote_dir
    }
    # 收集文件列表
    file_list = collect_file_list(sizes)
    # 计算总文件大小
    total_size_bytes = calc_total_size(file_list)
    total_size_mb = total_size_bytes / (1024 * 1024)
    # 构造命令
    rayfile_cmd = build_rayfilec_cmd(target_ip, target_port, username, password, file_list, remote_dir)
    # 打印并执行命令
    print("即将执行的rayfile-c命令：")
    print(' '.join(rayfile_cmd))
    start_time = time.time()
    subprocess.run(' '.join(rayfile_cmd), shell=True, check=True)
    end_time = time.time()
    elapsed = end_time - start_time
    print(f"文件传输总用时: {elapsed:.2f} 秒")
    print(f"文件总大小: {total_size_mb:.2f} MB")
    if elapsed > 0:
        avg_speed = total_size_mb / elapsed
        print(f"平均传输速率: {avg_speed:.2f} MB/s")
    else:
        print("平均传输速率: N/A")
        avg_speed = 0.0

    # 分文件类型统计及速率分析
    size_type_to_size = { name: sz for name, sz in sizes }
    per_type_files = {name: [] for name, sz in sizes}
    for fname in file_list:
        for name, sz in sizes:
            if fname.startswith(name):
                per_type_files[name].append(fname)
                break
    size_mb_list = []
    speed_list = []
    for name in per_type_files:
        files = per_type_files[name]
        size_bytes = sum(os.path.getsize(f) for f in files if os.path.exists(f))
        size_mb = size_bytes / (1024 * 1024)
        size_mb_list.append(f"{name}")
        # 估算各类型平均速率 = 各类型文件体积 / 总耗时
        # 更准确做法是分开传多次，但本工具按总速率给出
        s = size_mb / elapsed if elapsed > 0 else 0
        speed_list.append(s)

    # 画图
    speed_chart_file = "file_throughput_chart.png"
    plot_speed_chart(size_mb_list, speed_list, speed_chart_file)

    # 新增完整性校验
    print("开始校验文件完整性（md5）...")
    all_pass, check_details = check_files_integrity(file_list, ssh_ip, ssh_port, username, key_path, remote_dir)
    if all_pass:
        print("所有文件完整性校验通过！")
    else:
        print("部分文件完整性校验失败，请检查日志。")

    # 汇总统计
    stats = {
        "Total Time (s)": f"{elapsed:.2f}",
        "Total File Size (MB)": f"{total_size_mb:.2f}",
        "Average Transfer Speed (MB/s)": f"{avg_speed:.2f}",
    }

    # 生成PDF报告
    pdf_filename = "file_throughput_report.pdf"
    generate_pdf_report(
        pdf_filename=pdf_filename,
        items=file_list,
        speed_chart_png=speed_chart_file,
        config_info=config_info,
        overall_stats=stats,
        integrity_results=check_details,
    )
    print(f"PDF报告已生成: {pdf_filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='File Throughput Tester')
    parser.add_argument('-c', '--config', type=str, default='config.ini', help='配置文件路径，默认为config.ini')
    args = parser.parse_args()
    file_throughput(config_path=args.config)
