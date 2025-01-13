from time import time
from othello.board import Board
from typing import Literal
from concurrent.futures import ThreadPoolExecutor
from engine.settings import WEIGHTS, HEATMAP

import threading


transposition_lock = threading.Lock()

def find_noisy_moves_bitboard(black_bitboard, white_bitboard, color):
    threshold = 9
    legal_moves = find_legal_moves_bitboard(black_bitboard, white_bitboard, color)
    noisy_moves = 0
    for position in range(64):
            bit = 1 << position # Isolate the bit for this position
            
            # Check if the move is legal and meets the threshold
            if legal_moves & bit and HEATMAP[position] > threshold:
                noisy_moves |= bit  # Add the move to the result bitboard

    return noisy_moves

def quiescence_search(black_bitboard, white_bitboard, alpha, beta, color):
    # Stand-pat score: evaluate the current position without any moves
    stand_pat = eval_bitboard(black_bitboard, white_bitboard)
    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat

    # Generate only "noisy" moves (e.g., high-value flips)
    noisy_moves = find_noisy_moves_bitboard(black_bitboard, white_bitboard, color)
    while noisy_moves:
        move = noisy_moves & -noisy_moves
        noisy_moves &= noisy_moves - 1
        new_black_bitboard, new_white_bitboard = make_move_bitboard(black_bitboard, white_bitboard, color, move)
        
        score = -quiescence_search(new_white_bitboard, new_black_bitboard, -beta, -alpha, opponent_color(color))
        if score >= beta:
            return beta
        if score > alpha:
            alpha = score

    return alpha

def ai_move_iterative(board, color, max_depth, time_limit=5.0):
    best_move = None
    best_depth = 0
    if time_limit is not None:
        time_limit += time()
    for depth in range(1, max_depth + 1):
        new_move = ai_move(board, color, depth, {}, time_limit)
        if new_move[0] is not None:
            best_move = new_move
            best_depth = depth
        if time_limit is not None and time() > time_limit:
            break
    return best_move, best_depth

def ai_move(board: Board, color, depth=3, transposition_table={}, time_limit=None):
    best_score = float('-inf')
    best_move = None
    black_bitboard, white_bitboard = board_to_bitboard(board.board)
    legal_moves = find_legal_moves_bitboard(black_bitboard, white_bitboard, color)

    # Function to evaluate a single move
    def evaluate_move(move):
        new_black_bitboard, new_white_bitboard = make_move_bitboard(black_bitboard, white_bitboard, color, move)
        score = minimax_ab_bitboard_tt(
            new_black_bitboard, new_white_bitboard,
            depth-1, float('-inf'), float('inf'),
            False, opponent_color(color),
            transposition_table, time_limit
        )
        return move, score

    # Multithreaded evaluation
    with ThreadPoolExecutor() as executor:
        futures = []
        while legal_moves:
            move = legal_moves & -legal_moves  # Isolate the least significant bit (a single move)
            legal_moves &= legal_moves - 1  # Remove the LSB from the bitboard
            futures.append(executor.submit(evaluate_move, move))

        # Process results as threads complete
        for future in futures:
            if time_limit is not None and time() > time_limit:
                break
            move, score = future.result()
            if score > best_score:
                best_score = score
                best_move = move

    return move_to_notation(best_move), best_score

def minimax_ab_bitboard_tt(black_bitboard, white_bitboard, depth, alpha, beta, maximizing_player, color, transposition_table, time_limit=None):
    # Transposition Table
    board_hash = hash_bitboards(black_bitboard, white_bitboard)
    if board_hash in transposition_table:
        return get_from_tt(board_hash, transposition_table)
    
    if depth == 0 or game_over(black_bitboard, white_bitboard) or (time_limit is not None and time() > time_limit):
        return quiescence_search(black_bitboard, white_bitboard, alpha, beta, color)
    
    legal_moves = find_legal_moves_bitboard(black_bitboard, white_bitboard, color)
    if maximizing_player:
        if legal_moves == 0:# Pass to other player
            score = minimax_ab_bitboard_tt(black_bitboard, white_bitboard, depth-1, alpha, beta, False, opponent_color(color), transposition_table, time_limit)
            alpha = max(alpha, score)
            return score
        max_score = float('-inf')
        while legal_moves:
            move = legal_moves & - legal_moves
            legal_moves &= legal_moves - 1
            new_black_bitboard, new_white_bitboard = make_move_bitboard(black_bitboard, white_bitboard, color, move)
            score = minimax_ab_bitboard_tt(new_black_bitboard, new_white_bitboard, depth-1, alpha, beta, False, opponent_color(color), transposition_table, time_limit)
            max_score = max(max_score, score)
            alpha = max(alpha, score)
            if beta <= alpha:
                break
        store_in_tt(board_hash, max_score, transposition_table)
        return max_score
    else:
        if legal_moves == 0:# Pass to other player
            score = minimax_ab_bitboard_tt(black_bitboard, white_bitboard, depth-1, alpha, beta, True, opponent_color(color), transposition_table, time_limit)
            beta = min(beta, score)
            return score
        min_score = float('inf')
        while legal_moves:
            move = legal_moves & - legal_moves
            legal_moves &= legal_moves - 1
            new_black_bitboard, new_white_bitboard = make_move_bitboard(black_bitboard, white_bitboard, color, move)
            score = minimax_ab_bitboard_tt(new_black_bitboard, new_white_bitboard, depth-1, alpha, beta, True, opponent_color(color), transposition_table, time_limit)
            min_score = min(min_score, score)
            beta = min(beta, score)
            if beta <= alpha:
                break
        store_in_tt(board_hash, min_score, transposition_table)
        return min_score
    
def get_from_tt(board_hash, transposition_table):
    with transposition_lock:
        return transposition_table.get(board_hash)

def store_in_tt(board_hash, value, transposition_table):
    with transposition_lock:
        transposition_table[board_hash] = value

def hash_bitboards(board1, board2):
    prime = 0x9e3779b97f4a7c15  # A large 64-bit prime number
    hash_value = board1 + prime
    hash_value ^= board2 * prime
    return hash_value

def opponent_color(color):
    return 'w' if color == 'b' else 'b'

def board_to_bitboard(board):
    black = 0
    white = 0
    
    for x in range(8):
        for y in range(8):
            bit_index = x + y * 8  # No need to reverse the coordinates
            if board[x][y] == 'b':
                black |= 1 << bit_index  # Set bit for black
            elif board[x][y] == 'w':
                white |= 1 << bit_index  # Set bit for white
    
    return black, white

def find_legal_moves_bitboard(black_bitboard, white_bitboard, color):
    if color == 'b':
        player = black_bitboard
        opponent = white_bitboard
    else:
        player = white_bitboard
        opponent = black_bitboard
    legal_moves_bitboard = 0  # Start with an empty bitboard
    
    directions = [-1, 1, -8, 8, -7, 7, -9, 9]
    
    for i in range(64):  # Iterate over all 64 squares
        if (player | opponent) & (1 << i):  # Skip occupied squares
            continue
        
        for direction in directions:
            flip = False
            pos = i + direction
            
            # Check boundaries for left-right moves and row wrapping
            jumping = False
            while 0 <= pos < 64:
                if direction == -1 and pos % 8 == 0:  # If we're at the leftmost column
                    break
                if direction == 1 and pos % 8 == 7:   # If we're at the rightmost column
                    break

                if direction == -7 and pos % 8 == 7:
                    break
                if direction == 7 and pos % 8 == 0:
                    break

                if direction == -9 and pos % 8 == 0:
                    break
                if direction == 9 and pos % 8 == 7:
                    break

                # If we encounter the opponent's piece, continue checking
                if (opponent >> pos) & 1:
                    pos += direction
                    jumping = True
                # If we encounter the player's own piece, it's a valid move in this direction
                elif (player >> pos) & 1:
                    if jumping:
                        flip = True
                    break
                else:  # An empty square or boundary, break out
                    break
            
            if flip:
                legal_moves_bitboard |= (1 << i)  # Mark this square as a legal move

    return legal_moves_bitboard

def shift_board(bitboard, shift):
    """
    Shifts the bitboard in the specified direction while avoiding illegal board wrapping.
    Args:
        bitboard: The current player's bitboard.
        shift: The direction and distance to shift (positive or negative).
    Returns:
        The shifted bitboard.
    """
    if shift > 0:  # Shifting downwards or rightwards
        if shift % 8 == 0:  # Vertical shift (up/down)
            return bitboard >> shift
        elif shift == 1:  # Right shift
            return (bitboard >> shift) & 0x7F7F7F7F7F7F7F7F  # Mask to avoid wrapping
        elif shift == -1:  # Left shift
            return (bitboard << -shift) & 0xFEFEFEFEFEFEFEFE  # Mask to avoid wrapping
    else:  # Shifting upwards or leftwards
        shift = -shift
        if shift % 8 == 0:  # Vertical shift (up/down)
            return bitboard << shift
        elif shift == 1:  # Left shift
            return (bitboard << shift) & 0xFEFEFEFEFEFEFEFE  # Mask to avoid wrapping
        elif shift == -1:  # Right shift
            return (bitboard >> -shift) & 0x7F7F7F7F7F7F7F7F  # Mask to avoid wrapping
    return 0  # Return 0 if no valid shift is applied

def make_move_bitboard(black, white, color, move):
    if color == 'b':
        player = black
        opponent = white
    else:
        player = white
        opponent = black
    # Directions: [±1, ±8, ±7, ±9] (left, right, up, down, diagonals)
    DIRECTIONS = [-1, 1, -8, 8, -7, -9, 7, 9]
    flips = 0

    # Compute flips for all directions
    for direction in DIRECTIONS:
        flips |= compute_flips(move, player, opponent, direction)

    # Update bitboards
    player |= flips | move  # Add flipped pieces and the move to the player
    opponent &= ~flips      # Remove flipped pieces from the opponent

    if color == 'b':
        return player, opponent
    else:
        return opponent, player

def compute_flips(move, player, opponent, direction):
    """
    Compute the pieces flipped in a specific direction.
    """
    mask = 0
    potential = shift_board(move, direction) & opponent  # Check the first step
    while potential:
        mask |= potential  # Accumulate potential flips
        potential = shift_board(potential, direction) & opponent
    # Check if flips are valid (bracketed by a player piece)
    if shift_board(mask, direction) & player:
        return mask
    return 0


def eval_bitboard(black_bitboard:int, white_bitboard:int):
    # Each heuristic value scales from -100 to 100
    # Individual values are weighted at the end of the evaluation
    # https://kartikkukreja.wordpress.com/2013/03/30/heuristic-function-for-reversiothello/

    # Coin Parity
    max_discs = black_bitboard.bit_count()
    min_discs = white_bitboard.bit_count()
    coin_parity = 100 * (max_discs - min_discs) / (max_discs + min_discs)

    # Mobility
    max_moves = find_legal_moves_bitboard(black_bitboard, white_bitboard, 'b')
    min_moves = find_legal_moves_bitboard(black_bitboard, white_bitboard, 'b')
    max_count = max_moves.bit_count()
    min_count = min_moves.bit_count()
    mobility = 0
    if min_count + max_count > 0:
        mobility = 100 * (max_count - min_count) / (max_count + min_count)

    # Corners
    max_corners = 0
    min_corners = 0
    for position in (0, 8, 55, 63):
        if black_bitboard & (1<<position):
            max_corners += 1
        elif white_bitboard & (1<<position):
            min_corners += 1
    corners = 0
    if min_corners + max_corners > 0:
        corners = 100 * (max_corners - min_corners) / (max_corners + min_corners)

    # Stability
    max_stability = 0
    min_stability = 0

    # -1: unstable - can be captured next turn
    #  0: semi-stable - can't be captured next turn but may be captured later
    #  1: stable - can't be captured

    max_stable_map = create_stable_bitmap(black_bitboard, white_bitboard, 'b')
    max_unstable_map = create_unstable_bitmap(black_bitboard, white_bitboard, 'w', min_moves)
    min_stable_map = create_stable_bitmap(black_bitboard, white_bitboard, 'w')
    min_unstable_map = create_unstable_bitmap(black_bitboard, white_bitboard, 'b', max_moves)

    max_stability += max_stable_map.bit_count()
    max_stability -= max_unstable_map.bit_count()
    min_stability += min_stable_map.bit_count()
    max_stability -= min_unstable_map.bit_count()

    stability = 0
    if min_stability + max_stability > 0:
        stability = 100 * (max_stability - min_stability) / (max_stability + min_stability)

    # Weights
    max_weights = get_weights(black_bitboard)
    min_weights = get_weights(white_bitboard)

    weights = 0
    if min_weights + max_weights > 0:
        weights = 100 * (max_weights - min_weights) / (max_weights + min_weights)

    total_discs = max_discs + min_discs
    if total_discs < 20:
        game_phase = 'opening'
    elif total_discs < 40:
        game_phase = 'middlegame'
    else:
        game_phase = 'endgame'
    evaluation = 0
    evaluation += coin_parity * WEIGHTS[game_phase]['coin_parity']
    evaluation += mobility * WEIGHTS[game_phase]['mobility']
    evaluation += corners * WEIGHTS[game_phase]['corners']
    evaluation += stability * WEIGHTS[game_phase]['stability']
    evaluation += weights * WEIGHTS[game_phase]['weights']
    return evaluation

def get_weights(bitmap:int):
    
    score = 0
    while bitmap:
        square = (bitmap & - bitmap).bit_length() - 1
        bitmap &= bitmap - 1
        score += HEATMAP[square]
    return score

def game_over(black_bitboard, white_bitboard):
    if find_legal_moves_bitboard(black_bitboard, white_bitboard, 'b') != 0:
        return False
    if find_legal_moves_bitboard(black_bitboard, white_bitboard, 'w') != 0:
        return False
    return True

def move_to_notation(move:int):
    """
    Convert a single-bit bitboard move to Othello notation (e.g., A1, H8).
    Args:
        move: A single-bit bitboard representing the move.
    Returns:
        A string in Othello notation (e.g., "E3").
    """
    if move == 0:
        return "Pass"  # If no move is made
    try:
        index = move.bit_length() - 1  # Get the index of the single '1' bit
        row = index // 8               # Calculate 0-indexed row
        col = index % 8                # Calculate 0-indexed column
        # Convert to Othello notation
        return f"{chr(col + ord('A'))}{row + 1}"
    except:
        return

def create_unstable_bitmap(black_bitmap, white_bitmap, color:Literal['b', 'w'], legal_moves) -> int:
    unstable_bitmap = (1 << 64) - 1
    while legal_moves:
        move = legal_moves & - legal_moves
        legal_moves &= legal_moves - 1
        unstable_bitmap &= make_move_bitboard(black_bitmap, white_bitmap, color, move)['wb'.find(color)]
    return unstable_bitmap

def create_stable_bitmap(black_bitmap, white_bitmap, color:Literal['b', 'w']) -> int:
    stable_bitmap = 0

    # Iterate from all corners (because corners cant be captured)
    for i in (0, 7, 55, 63):
        directions = {
            0: (1, 8),
            7: (-1, 8),
            55: (1, -8),
            63: (-1, -8)
        }[i]
        iterate_stable_map(i, directions, black_bitmap, white_bitmap, color, stable_bitmap)
    
    return stable_bitmap

def iterate_stable_map(pos:int, directions:tuple, black_bitmap, white_bitmap, color:Literal['b', 'w'], stable_bitmap:int):
    # Check if two adjacent stable discs are present
    for d in directions:
        if d == -1 and pos % 8 == 7:  # If we're at the rightmost column
            continue
        if d == 1 and pos % 8 == 0:   # If we're at the leftmost column
            continue
        if pos+d < 0 or pos+d > 63:
            continue
        if not stable_bitmap & (1 << pos+d):
            return
    stable_bitmap |= 1 << pos  # Set bit

    # Iterate horizontally
    for d in directions:
        if d == -1 and pos % 8 == 7:  # If we're at the rightmost column
            continue
        if d == 1 and pos % 8 == 0:   # If we're at the leftmost column
            continue
        if pos+d < 0 or pos+d > 63:
            continue
        iterate_stable_map(pos+d, directions, black_bitmap, white_bitmap, color, stable_bitmap)
