import rtmidi as midi
import keyboard as kb


def keyboard():
    if kb.is_pressed("1"):
        print("1")
    if kb.is_pressed("2"):
        print("2")
    if kb.is_pressed("3"):
        print("3")
    if kb.is_pressed("4"):
        print("4")
    if kb.is_pressed("5"):
        print("5")
    if kb.is_pressed("6"):
        print("6")
    if kb.is_pressed("7"):
        print("7")
    if kb.is_pressed("8"):
        print("8")
    if kb.is_pressed("9"):
        print("9")
    if kb.is_pressed("0"):
        print("0")

    if kb.is_pressed("q"):
        print("q")
    if kb.is_pressed("w"):
        print("w")
    if kb.is_pressed("e"):
        print("e")
    if kb.is_pressed("r"):
        print("r")
    if kb.is_pressed("t"):
        print("t")
    if kb.is_pressed("y"):
        print("y")
    if kb.is_pressed("u"):
        print("u")
    if kb.is_pressed("i"):
        print("i")
    if kb.is_pressed("p"):
        print("p")
    
    if kb.is_pressed("a"):
        print("a")
    if kb.is_pressed("s"):
        print("s")
    if kb.is_pressed("d"):
        print("d")
    if kb.is_pressed("f"):
        print("f")
    if kb.is_pressed("g"):
        print("g")
    if kb.is_pressed("h"):
        print("h")
    if kb.is_pressed("j"):
        print("j")
    if kb.is_pressed("k"):
        print("k")
    if kb.is_pressed("l"):
        print("l")
    if kb.is_pressed(";"):
        print(";")
    
    if kb.is_pressed("z"):
        print("z")
    if kb.is_pressed("x"):
        print("x")
    if kb.is_pressed("c"):
        print("c")
    if kb.is_pressed("v"):
        print("v")
    if kb.is_pressed("b"):
        print("b")
    if kb.is_pressed("n"):
        print("n")
    if kb.is_pressed("m"):
        print("m")
    if kb.is_pressed(","):
        print(",")
    if kb.is_pressed("."):
        print(".")


def keyboard_quit():
    if kb.is_pressed("esc"):
        return False

